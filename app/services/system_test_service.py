from dataclasses import asdict, dataclass
from time import perf_counter
from typing import Callable

from sqlalchemy.orm import Session


@dataclass
class TestResult:
    test_id: str
    layer: str
    name: str
    status: str
    expected: str
    actual: str
    detail: str
    duration_ms: float


def execute_case(
    test_id: str,
    layer: str,
    name: str,
    expected: str,
    callback: Callable,
) -> dict:
    started_at = perf_counter()

    try:
        passed, actual, detail = callback()

        status = (
            "PASS"
            if passed
            else "FAIL"
        )

    except Exception as error:
        status = "FAIL"
        actual = "Exception"
        detail = str(error)

    result = TestResult(
        test_id=test_id,
        layer=layer,
        name=name,
        status=status,
        expected=expected,
        actual=str(actual),
        detail=str(detail),
        duration_ms=round(
            (
                perf_counter()
                - started_at
            )
            * 1000,
            2,
        ),
    )

    return asdict(result)


def summarize(
    suite: str,
    results: list[dict],
) -> dict:
    total = len(results)

    passed = sum(
        item["status"] == "PASS"
        for item in results
    )

    failed = sum(
        item["status"] == "FAIL"
        for item in results
    )

    skipped = sum(
        item["status"] == "SKIP"
        for item in results
    )

    pass_rate = 0

    if total:
        pass_rate = round(
            passed / total * 100,
            2,
        )

    return {
        "suite": suite,
        "status": (
            "PASS"
            if failed == 0
            else "FAIL"
        ),
        "total": total,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "pass_rate": pass_rate,
        "results": results,
    }


# =========================================================
# KIỂM THỬ LOGIC NỘI BỘ
# =========================================================

def run_internal_tests(
    db: Session,
) -> list[dict]:
    from app.routers.chat import (
        build_local_answer,
        detect_topics,
        find_procedure,
        is_form_question,
        is_greeting,
        normalize_text,
    )

    results = []

    # UT01
    def normalize_case():
        actual = normalize_text(
            "Đăng ký thường trú"
        )

        passed = (
            actual
            == "dang ky thuong tru"
        )

        return (
            passed,
            actual,
            "Chuẩn hóa tiếng Việt.",
        )

    results.append(
        execute_case(
            test_id="UT01",
            layer="Unit / White-box",
            name="Chuẩn hóa tiếng Việt",
            expected="dang ky thuong tru",
            callback=normalize_case,
        )
    )

    # UT02
    def greeting_case():
        valid = is_greeting(
            "Xin chào"
        )

        invalid = is_greeting(
            "Thủ tục cấp lại hộ chiếu"
        )

        passed = valid and not invalid

        return (
            passed,
            (
                f"valid={valid}; "
                f"invalid={invalid}"
            ),
            "Nhận diện câu chào độc lập.",
        )

    results.append(
        execute_case(
            test_id="UT02",
            layer="Unit / White-box",
            name="Nhận diện câu chào",
            expected=(
                "Câu chào đúng, câu hỏi khác "
                "không bị nhận nhầm"
            ),
            callback=greeting_case,
        )
    )

    # UT03
    def topic_case():
        topics = detect_topics(
            "Đăng ký thường trú "
            "cần giấy tờ gì?"
        )

        passed = (
            "permanent_residence"
            in topics
        )

        return (
            passed,
            str(topics),
            "Nhận diện chủ đề thường trú.",
        )

    results.append(
        execute_case(
            test_id="UT03",
            layer="Unit / White-box",
            name="Nhận diện chủ đề",
            expected=(
                "Có permanent_residence"
            ),
            callback=topic_case,
        )
    )

    # UT04
    def wrong_topic_case():
        topics = detect_topics(
            "Thủ tục cấp lại hộ chiếu"
        )

        passed = (
            "passport" in topics
            and "permanent_residence"
            not in topics
        )

        return (
            passed,
            str(topics),
            "Không gán hộ chiếu vào "
            "thường trú.",
        )

    results.append(
        execute_case(
            test_id="UT04",
            layer="Unit / White-box",
            name=(
                "Từ chối câu hỏi ngoài chủ đề"
            ),
            expected=(
                "Có passport, không có "
                "permanent_residence"
            ),
            callback=wrong_topic_case,
        )
    )

    # IT01
    def local_case():
        procedure = find_procedure(
            db,
            "Đăng ký thường trú "
            "thực hiện ở đâu?",
        )

        passed = (
            procedure is not None
            and "thường trú"
            in procedure.name.lower()
        )

        actual = (
            procedure.name
            if procedure
            else "Không tìm thấy"
        )

        return (
            passed,
            actual,
            "Tìm thủ tục trong CSDL nội bộ.",
        )

    results.append(
        execute_case(
            test_id="IT01",
            layer="Integration",
            name="Tìm thủ tục nội bộ",
            expected=(
                "Tìm thấy Đăng ký thường trú"
            ),
            callback=local_case,
        )
    )

    # IT02
    def passport_case():
        procedure = find_procedure(
            db,
            "Thủ tục cấp lại hộ chiếu "
            "cần làm gì?",
        )

        passed = procedure is None

        actual = (
            procedure.name
            if procedure
            else "Không chọn thường trú"
        )

        return (
            passed,
            actual,
            "Không trả nhầm thủ tục.",
        )

    results.append(
        execute_case(
            test_id="IT02",
            layer="Integration",
            name=(
                "Không trả nhầm thủ tục hộ chiếu"
            ),
            expected=(
                "Không chọn đăng ký thường trú"
            ),
            callback=passport_case,
        )
    )

    # ST01
    def answer_case():
        procedure = find_procedure(
            db,
            "Đăng ký thường trú "
            "thực hiện ở đâu?",
        )

        if procedure is None:
            return (
                False,
                "Không tìm thấy thủ tục",
                "CSDL không có dữ liệu.",
            )

        answer, sources = build_local_answer(
            db,
            procedure,
            "Đăng ký thường trú "
            "thực hiện ở đâu?",
        )

        passed = "Công an" in answer

        return (
            passed,
            answer,
            f"Số nguồn: {len(sources)}",
        )

    results.append(
        execute_case(
            test_id="ST01",
            layer="System / Black-box",
            name="Trả lời nơi thực hiện",
            expected=(
                "Câu trả lời có thông tin Công an"
            ),
            callback=answer_case,
        )
    )

    # ST02
    def form_case():
        question = (
            "Tôi muốn xin mẫu đơn "
            "đăng ký thường trú"
        )

        procedure = find_procedure(
            db,
            question,
        )

        if procedure is None:
            return (
                False,
                "Không tìm thấy thủ tục",
                "Không kiểm tra được biểu mẫu.",
            )

        answer, _ = build_local_answer(
            db,
            procedure,
            question,
        )

        link_count = answer.count(
            "Link biểu mẫu:"
        )

        passed = (
            is_form_question(
                "Tôi muốn xin mẫu CT01"
            )
            and link_count == 1
        )

        return (
            passed,
            f"link_count={link_count}",
            "CT01 chỉ hiển thị một lần.",
        )

    results.append(
        execute_case(
            test_id="ST02",
            layer="System / Black-box",
            name="Kiểm tra biểu mẫu CT01",
            expected=(
                "Có CT01 và chỉ có một link"
            ),
            callback=form_case,
        )
    )

    results.extend(
        run_acceptance_ai_regression_tests(db)
    )

    return results


# =========================================================
# ACCEPTANCE / AI / REGRESSION
# =========================================================

def run_acceptance_ai_regression_tests(
    db: Session,
) -> list[dict]:
    """
    - AT: kiểm thử chấp nhận theo User Story (gọi trực tiếp API chat).
    - AI: 3 ca kiểm thử AI bắt buộc (grounding, không bịa, giữ ngữ cảnh).
    - RT: kiểm thử hồi quy cho các lỗi đã phát hiện và đã sửa.
    """

    import re
    import uuid

    from app.models import ChatHistory
    from app.routers.chat import chat
    from app.services.ai_service import build_grounded_prompt
    from app.services.retrieval_service import (
        build_context,
        find_candidate_procedures,
    )

    session_id = f"systemtest-{uuid.uuid4().hex[:12]}"
    results = []

    def ask(question: str) -> dict:
        return chat(
            question=question,
            file=None,
            session_id=session_id,
            db=db,
        )

    def first_text(response: dict) -> str:
        blocks = response.get("answer_blocks") or []
        return blocks[0].get("content", "") if blocks else ""

    def first_label(response: dict) -> str:
        blocks = response.get("answer_blocks") or []
        return blocks[0].get("source_label", "") if blocks else ""

    # ---------- ACCEPTANCE (User Story) ----------
    acceptance_cases = [
        (
            "AT01",
            "US01 - Tra cứu hồ sơ đăng ký tạm trú",
            "Đăng ký tạm trú cần giấy tờ gì?",
            lambda r: first_label(r) == "CSDL NỘI BỘ"
            and "CT01" in first_text(r),
            "Trả lời từ CSDL nội bộ, có tờ khai CT01",
        ),
        (
            "AT02",
            "US02 - Hỏi nơi thực hiện",
            "Đăng ký thường trú ở đâu?",
            lambda r: "Công an" in first_text(r),
            "Câu trả lời nêu cơ quan Công an",
        ),
        (
            "AT03",
            "US03 - Hỏi thời hạn giải quyết",
            "Gia hạn tạm trú mất bao lâu?",
            lambda r: "ngày" in first_text(r).lower(),
            "Câu trả lời có số ngày giải quyết",
        ),
        (
            "AT04",
            "US04 - Hiển thị nguồn thủ tục",
            "Thủ tục tách hộ cần giấy tờ gì?",
            lambda r: len(r.get("sources") or []) >= 1,
            "Có ít nhất 1 nguồn tham khảo",
        ),
    ]

    for test_id, name, question, check, expected in acceptance_cases:
        def acceptance_case(question=question, check=check):
            response = ask(question)
            return (
                bool(check(response)),
                first_text(response)[:200],
                f"route={response.get('route')}",
            )

        results.append(
            execute_case(
                test_id=test_id,
                layer="Acceptance",
                name=name,
                expected=expected,
                callback=acceptance_case,
            )
        )

    # ---------- AI ----------
    # AI01: Có dữ liệu -> prompt RAG chứa đúng dữ liệu và quy tắc không bịa
    def ai_grounding_case():
        question = "Cấp đổi thẻ căn cước cần những gì?"
        candidates = find_candidate_procedures(db, question, k=3)
        context = build_context(db, candidates)
        prompt = build_grounded_prompt(question, context)

        codes = [c.procedure_code for c in candidates]
        passed = (
            bool(candidates)
            and "2.001195" in codes
            and "Chỉ trả lời dựa trên" in prompt
            and "[MÃ THỦ TỤC:" in prompt
        )

        return (
            passed,
            f"Thủ tục ngữ cảnh: {codes}",
            "Prompt chứa dữ liệu MySQL và quy tắc chỉ dùng dữ liệu.",
        )

    results.append(
        execute_case(
            test_id="AI01",
            layer="AI / Grounding",
            name="Có dữ liệu: ngữ cảnh RAG đúng thủ tục",
            expected="Ngữ cảnh chứa thủ tục 2.001195",
            callback=ai_grounding_case,
        )
    )

    # AI02: Thiếu dữ liệu -> không bịa số văn bản, lệ phí
    def ai_no_hallucination_case():
        response = ask("Làm hộ chiếu phổ thông cần giấy tờ gì và lệ phí bao nhiêu?")
        text = first_text(response)

        has_fake_detail = bool(
            re.search(r"\d+/\d{4}/(TT|NĐ|ND|QH)", text)
            or re.search(r"\d[\d.]*\s*(đồng|vnđ|vnd)", text.lower())
        )

        passed = (
            response.get("route")
            in {"gemini_out_of_scope", "no_data"}
            and not response.get("sources")
            and not has_fake_detail
        )

        return (
            passed,
            text[:200],
            f"route={response.get('route')}",
        )

    results.append(
        execute_case(
            test_id="AI02",
            layer="AI / Hallucination",
            name="Thiếu dữ liệu: không bịa thông tin",
            expected="Không nêu số văn bản hoặc lệ phí cụ thể",
            callback=ai_no_hallucination_case,
        )
    )

    # AI03: Hỏi tiếp -> giữ ngữ cảnh thủ tục
    def ai_followup_case():
        first = ask("Đăng ký tạm trú cần giấy tờ gì?")
        second = ask("Thế lệ phí bao nhiêu?")

        passed = (
            first.get("procedure_code")
            and second.get("procedure_code")
            == first.get("procedure_code")
        )

        return (
            bool(passed),
            first_text(second)[:200],
            f"{first.get('procedure_code')} -> {second.get('procedure_code')}",
        )

    results.append(
        execute_case(
            test_id="AI03",
            layer="AI / Context",
            name="Hỏi tiếp: giữ ngữ cảnh hội thoại",
            expected="Câu hỏi thứ hai dùng lại thủ tục của câu đầu",
            callback=ai_followup_case,
        )
    )

    # ---------- REGRESSION: các lỗi đã sửa ----------
    regression_cases = [
        (
            "RT01",
            "Lỗi #1: 'những bước' không được nhận diện",
            "Tách hộ cần những bước nào?",
            lambda r: "bước" in first_text(r).lower()
            and r.get("procedure_code") == "1.010038",
            "Liệt kê các bước của thủ tục Tách hộ",
        ),
        (
            "RT02",
            "Lỗi #2: 'xác nhận cư trú' bị chuyển sang Gemini",
            "Cho tôi hỏi về xác nhận cư trú",
            lambda r: r.get("procedure_code") == "1.010041",
            "Trả lời từ thủ tục 1.010041",
        ),
        (
            "RT03",
            "Lỗi #3: 'chuyển nhà' không tìm được thủ tục",
            "Tôi chuyển nhà sang xã khác thì phải làm gì?",
            lambda r: r.get("route") == "local_suggestion"
            and "thường trú" in first_text(r).lower()
            and "tạm trú" in first_text(r).lower(),
            "Gợi ý cả Đăng ký thường trú và Đăng ký tạm trú",
        ),
        (
            "RT04",
            "Lỗi #4: câu ngoài phạm vi bị gán nhầm thủ tục của câu trước",
            "Thủ tục đăng ký kết hôn cần gì?",
            lambda r: not r.get("procedure_code")
            and r.get("route") != "local_followup",
            "Không dùng lại thủ tục của câu hỏi trước",
        ),
        (
            "RT05",
            "Lỗi #5: câu hỏi chung bị lấy thủ tục căn cước làm ngữ cảnh",
            "Việt Nam có bao nhiêu dân tộc",
            lambda r: not r.get("procedure_code")
            and r.get("route") in {"no_data", "gemini_out_of_scope", "gemini_general"},
            "Không đưa thủ tục căn cước vào ngữ cảnh",
        ),
        (
            "RT06",
            "Lỗi #6: câu hỏi kép chỉ trả lời một phần",
            "Tôi bị mất hộ chiếu và căn cước công dân thì cần phải làm gì",
            lambda r: r.get("route") == "compound"
            and len(r.get("answer_blocks") or []) == 2
            and r.get("procedure_code") == "2.001194",
            "Trả lời cả phần hộ chiếu (ngoài dữ liệu) và phần căn cước (CSDL)",
        ),
    ]

    for test_id, name, question, check, expected in regression_cases:
        def regression_case(question=question, check=check):
            response = ask(question)
            return (
                bool(check(response)),
                first_text(response)[:200],
                f"route={response.get('route')}",
            )

        results.append(
            execute_case(
                test_id=test_id,
                layer="Regression",
                name=name,
                expected=expected,
                callback=regression_case,
            )
        )

    # Dọn lịch sử do kiểm thử tạo ra
    try:
        db.query(ChatHistory).filter(
            ChatHistory.session_id == session_id
        ).delete(synchronize_session=False)
        db.commit()
    except Exception:
        db.rollback()

    return results


# =========================================================
# SELENIUM
# =========================================================

def create_driver():
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options

    options = Options()

    options.add_argument(
        "--headless=new"
    )

    options.add_argument(
        "--disable-gpu"
    )

    options.add_argument(
        "--no-sandbox"
    )

    options.add_argument(
        "--disable-dev-shm-usage"
    )

    options.add_argument(
        "--window-size=1440,1000"
    )

    return webdriver.Chrome(
        options=options
    )


def build_chat_url(
    base_url: str,
) -> str:
    """
    Giao diện CivicBot nằm tại /chat.
    Địa chỉ / chỉ trả về thông tin API.
    """

    base_url = (
        base_url or ""
    ).rstrip("/")

    if base_url.endswith("/chat"):
        return base_url

    return f"{base_url}/chat"


def get_bot_messages(driver):
    from selenium.webdriver.common.by import By

    return driver.find_elements(
        By.CSS_SELECTOR,
        ".message-row.bot",
    )


def send_ui_question(
    driver,
    question: str,
) -> str:
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import (
        WebDriverWait,
    )
    from selenium.webdriver.support import (
        expected_conditions as EC,
    )

    wait = WebDriverWait(
        driver,
        30,
    )

    input_element = wait.until(
        EC.presence_of_element_located(
            (
                By.ID,
                "questionInput",
            )
        )
    )

    send_button = wait.until(
        EC.element_to_be_clickable(
            (
                By.ID,
                "sendButton",
            )
        )
    )

    old_count = len(
        get_bot_messages(driver)
    )

    input_element.clear()
    input_element.send_keys(question)
    send_button.click()

    wait.until(
        lambda current_driver: len(
            get_bot_messages(
                current_driver
            )
        )
        > old_count
    )

    messages = get_bot_messages(
        driver
    )

    return messages[-1].text


def run_ui_tests(
    base_url: str,
) -> list[dict]:
    results = []
    driver = None

    try:
        driver = create_driver()

        # Điểm sửa quan trọng:
        # Mở /chat thay vì /
        driver.get(
            build_chat_url(base_url)
        )

        # UI01
        def page_case():
            passed = (
                "CivicBot"
                in driver.page_source
            )

            return (
                passed,
                (
                    "CivicBot"
                    if passed
                    else "Không tìm thấy CivicBot"
                ),
                "Trang giao diện đã tải.",
            )

        results.append(
            execute_case(
                test_id="UI01",
                layer="UI / Black-box",
                name="Mở giao diện CivicBot",
                expected=(
                    "Trang có CivicBot"
                ),
                callback=page_case,
            )
        )

        # UI02
        def question_case():
            answer = send_ui_question(
                driver,
                "Đăng ký thường trú "
                "thực hiện ở đâu?",
            )

            passed = (
                "Công an" in answer
                or "CSDL NỘI BỘ"
                in answer
            )

            return (
                passed,
                answer,
                "Gửi câu hỏi trên giao diện.",
            )

        results.append(
            execute_case(
                test_id="UI02",
                layer="UI / Black-box",
                name="Gửi câu hỏi nội bộ",
                expected=(
                    "Có câu trả lời nội bộ"
                ),
                callback=question_case,
            )
        )

        # UI03
        def form_case():
            answer = send_ui_question(
                driver,
                "Tôi muốn xin mẫu đơn "
                "đăng ký thường trú",
            )

            link_count = answer.count(
                "Link biểu mẫu:"
            )

            passed = (
                "CT01" in answer
                and link_count == 1
            )

            return (
                passed,
                (
                    f"link_count={link_count}; "
                    f"{answer}"
                ),
                "CT01 không bị lặp.",
            )

        results.append(
            execute_case(
                test_id="UI03",
                layer="UI / Black-box",
                name="Kiểm tra biểu mẫu CT01",
                expected=(
                    "Có CT01 và chỉ có một link"
                ),
                callback=form_case,
            )
        )

    except Exception as error:
        results.append(
            {
                "test_id": "UI-SETUP",
                "layer": "UI / Black-box",
                "name": (
                    "Khởi tạo Selenium"
                ),
                "status": "FAIL",
                "expected": (
                    "ChromeDriver hoạt động"
                ),
                "actual": (
                    "Không khởi tạo được"
                ),
                "detail": str(error),
                "duration_ms": 0,
            }
        )

    finally:
        if driver is not None:
            driver.quit()

    return results


def run_test_suite(
    suite: str,
    db: Session,
    base_url: str,
) -> dict:
    suite = (
        suite or "regression"
    ).lower().strip()

    results = []

    if suite in {
        "quick",
        "regression",
        "all",
    }:
        results.extend(
            run_internal_tests(db)
        )

    if suite in {
        "ui",
        "regression",
        "all",
    }:
        results.extend(
            run_ui_tests(base_url)
        )

    valid_suites = {
        "quick",
        "ui",
        "regression",
        "all",
    }

    if suite not in valid_suites:
        return summarize(
            suite,
            [
                {
                    "test_id": "SYSTEM-001",
                    "layer": "System",
                    "name": (
                        "Tên bộ kiểm thử"
                    ),
                    "status": "FAIL",
                    "expected": (
                        "quick, ui, "
                        "regression hoặc all"
                    ),
                    "actual": suite,
                    "detail": (
                        "Tên bộ kiểm thử "
                        "không hợp lệ."
                    ),
                    "duration_ms": 0,
                }
            ],
        )

    return summarize(
        suite,
        results,
    )