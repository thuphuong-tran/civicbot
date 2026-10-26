import argparse
from pathlib import Path

from app import models
from app.database import (
    Base,
    SessionLocal,
    engine,
)
from app.services.docx_import_service import (
    DocxImportError,
    parse_docx,
    upsert_procedure,
)


# Đảm bảo SQLAlchemy nhận diện model
_ = models

Base.metadata.create_all(
    bind=engine
)


def print_preview(
    file_path: Path,
    data: dict,
):
    procedure = data["procedure"]
    forms = data.get("forms", [])
    legal_references = data.get(
        "legal_references",
        [],
    )

    print("=" * 70)
    print(
        f"FILE: {file_path.name}"
    )
    print("-" * 70)

    print(
        "Mã thủ tục:",
        procedure.get(
            "procedure_code",
            "",
        ),
    )

    print(
        "Tên thủ tục:",
        procedure.get(
            "name",
            "",
        ),
    )

    print(
        "Nhóm thủ tục:",
        procedure.get(
            "category",
            "",
        ),
    )

    print(
        "Cơ quan thực hiện:",
        procedure.get(
            "authority",
            "",
        ),
    )

    print(
        "URL nguồn:",
        procedure.get(
            "source_url",
            "",
        ),
    )

    print(
        "Số bước:",
        len(data.get("steps", [])),
    )

    print(
        "Số giấy tờ:",
        len(data.get("documents", [])),
    )

    print(
        "Số biểu mẫu:",
        len(forms),
    )

    for index, form in enumerate(
        forms,
        start=1,
    ):
        print(
            f"- Biểu mẫu {index}:"
        )
        print(
            f"  Mã: {form.get('code', '')}"
        )
        print(
            f"  Tên: {form.get('name', '')}"
        )
        print(
            "  Điều kiện: "
            f"{form.get('condition', '')}"
        )
        print(
            "  Link: "
            f"{form.get('form_url', '')}"
        )

    print(
        "Số căn cứ pháp lý:",
        len(legal_references),
    )

    for index, reference in enumerate(
        legal_references,
        start=1,
    ):
        print(
            f"- Căn cứ {index}: "
            f"{reference.get('document_name', '')}"
        )
        print(
            "  Số: "
            f"{reference.get('document_number', '')}"
        )

    print("=" * 70)


def import_one_file(
    file_path: Path,
    dry_run: bool = False,
) -> bool:
    try:
        data = parse_docx(
            file_path
        )

        print_preview(
            file_path,
            data,
        )

        if dry_run:
            print(
                "DRY-RUN: Chưa lưu vào database."
            )
            return True

        db = SessionLocal()

        try:
            result = upsert_procedure(
                db=db,
                data=data,
            )

            db.commit()

            print(
                "Đã nhập thành công."
            )

            print(
                f"- Mã thủ tục: "
                f"{result['procedure_code']}"
            )

            print(
                f"- Trạng thái: "
                f"{result['action']}"
            )

            print(
                f"- Số bước: "
                f"{result['steps_count']}"
            )

            print(
                f"- Số giấy tờ: "
                f"{result['documents_count']}"
            )

            print(
                f"- Số biểu mẫu: "
                f"{result['forms_count']}"
            )

            print(
                f"- Số căn cứ pháp lý: "
                f"{result['legal_references_count']}"
            )

            return True

        except Exception:
            db.rollback()
            raise

        finally:
            db.close()

    except DocxImportError as error:
        print(
            f"LỖI FILE {file_path.name}:"
        )
        print(error)
        return False

    except Exception as error:
        print(
            f"LỖI KHÔNG XÁC ĐỊNH "
            f"Ở FILE {file_path.name}:"
        )
        print(error)
        return False


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Nhập dữ liệu thủ tục từ file Word "
            "vào CSDL CivicBot."
        )
    )

    parser.add_argument(
        "--file",
        help="Đường dẫn đến file .docx",
    )

    parser.add_argument(
        "--all",
        action="store_true",
        help="Nhập toàn bộ file thủ tục trong data/procedures",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Chỉ kiểm tra file, "
            "không lưu vào database."
        ),
    )

    args = parser.parse_args()

    if args.all:
        files = sorted(Path("data/procedures").glob("[12]*.docx"))
        ok = sum(
            bool(import_one_file(file_path=path, dry_run=args.dry_run))
            for path in files
        )
        print(f"Hoàn tất: {ok}/{len(files)} thủ tục.")
        return

    if not args.file:
        parser.error("Cần --file <đường dẫn> hoặc --all")

    file_path = Path(
        args.file
    )

    if not file_path.exists():
        print(
            f"Không tìm thấy file: {file_path}"
        )
        return

    success = import_one_file(
        file_path=file_path,
        dry_run=args.dry_run,
    )

    if success:
        print("Hoàn tất.")


if __name__ == "__main__":
    main()