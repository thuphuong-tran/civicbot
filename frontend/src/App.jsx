import {
    useEffect,
    useRef,
    useState,
} from "react";

import {
    checkGemini,
    clearHistory,
    deleteHistory,
    getAdminKey,
    getHistory,
    getSystemStatus,
    runSystemTests,
    sendChat,
    setAdminKey,
} from "./services/api";


const initialMessage = {
    role: "bot",
    blocks: [
        {
            content:
                "Xin chào! Tôi là CivicBot. " +
                "Tôi có thể giúp bạn tra cứu " +
                "thủ tục cư trú và giấy tờ tùy thân.",
            source_type: "local",
            source_label: "CSDL NỘI BỘ",
            meta:
                "Dữ liệu nội bộ luôn được ưu tiên " +
                "trước khi chuyển sang Gemini.",
        },
    ],
    sources: [],
    createdAt: new Date(),
};


const suggestions = [
    {
        text:
            "Đăng ký tạm trú cần giấy tờ gì?",
        value:
            "Đăng ký tạm trú cần giấy tờ gì?",
    },
    {
        text:
            "Khai báo tạm vắng cần làm gì?",
        value:
            "Khai báo tạm vắng cần làm gì?",
    },
    {
        text:
            "Cấp lại thẻ căn cước cần giấy tờ gì?",
        value:
            "Cấp lại thẻ căn cước cần giấy tờ gì?",
    },
];


function formatTime(dateValue) {
    const date = new Date(
        dateValue || Date.now()
    );

    return date.toLocaleTimeString(
        "vi-VN",
        {
            hour: "2-digit",
            minute: "2-digit",
        }
    );
}


function getSourceClass(sourceType) {
    if (sourceType === "local") {
        return "source-local";
    }

    if (sourceType === "gemini") {
        return "source-gemini";
    }

    return "source-system";
}


function MessageBlock({
    block,
}) {
    return (
        <div className="answer-block">
            <div
                className={
                    `message-source ${
                        getSourceClass(
                            block.source_type
                        )
                    }`
                }
            >
                {block.source_label ||
                    "HỆ THỐNG"}
            </div>

            <div className="message-content">
                {block.content || ""}
            </div>

            {block.meta && (
                <div className="message-meta">
                    {block.meta}
                </div>
            )}
        </div>
    );
}


function ChatMessage({
    message,
}) {
    const isUser =
        message.role === "user";

    return (
        <div
            className={
                `message-row ${
                    isUser
                        ? "user"
                        : "bot"
                }`
            }
        >
            <div className="message">
                <div
                    className={
                        `message-box ${
                            isUser
                                ? "user-box"
                                : ""
                        }`
                    }
                >
                    {message.blocks?.map(
                        (
                            block,
                            index
                        ) => (
                            <MessageBlock
                                key={index}
                                block={block}
                            />
                        )
                    )}

                    {message.fileName && (
                        <div className="file-message">
                            📎{" "}
                            {message.fileName}
                        </div>
                    )}

                    {!isUser &&
                        message.sources &&
                        message.sources.length > 0 && (
                            <div className="sources">
                                <div className="sources-title">
                                    Nguồn thủ tục
                                </div>

                                {message.sources.map(
                                    (
                                        source,
                                        index
                                    ) => (
                                        <a
                                            key={index}
                                            className="source-link"
                                            href={
                                                source.url
                                            }
                                            target="_blank"
                                            rel="noreferrer"
                                        >
                                            {source.title ||
                                                source.url}
                                        </a>
                                    )
                                )}
                            </div>
                        )}

                    <div className="message-time">
                        {formatTime(
                            message.createdAt
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}


// Hộp thoại xác nhận dùng chung, thay cho window.confirm / window.prompt
// của trình duyệt để thống nhất với giao diện CivicBot.
function ConfirmDialog({
    open,
    title,
    message,
    confirmLabel = "Xác nhận",
    cancelLabel = "Hủy",
    variant = "primary",
    confirmDisabled = false,
    onConfirm,
    onCancel,
    children,
}) {
    useEffect(() => {
        if (!open) {
            return undefined;
        }

        function handleKey(event) {
            if (event.key === "Escape") {
                onCancel();
            }
        }

        window.addEventListener("keydown", handleKey);

        return () =>
            window.removeEventListener("keydown", handleKey);
    }, [open, onCancel]);

    if (!open) {
        return null;
    }

    return (
        <div
            className="modal-backdrop confirm-backdrop"
            onClick={(event) => {
                if (event.target === event.currentTarget) {
                    onCancel();
                }
            }}
        >
            <form
                className="confirm-dialog"
                role="alertdialog"
                aria-modal="true"
                aria-labelledby="confirm-title"
                onSubmit={(event) => {
                    event.preventDefault();

                    if (!confirmDisabled) {
                        onConfirm();
                    }
                }}
            >
                <div className={`confirm-icon ${variant}`}>
                    {variant === "danger" ? "!" : "🔒"}
                </div>

                <h3 id="confirm-title">{title}</h3>

                {message && (
                    <p className="confirm-message">{message}</p>
                )}

                {children}

                <div className="confirm-actions">
                    <button
                        className="secondary-button"
                        type="button"
                        onClick={onCancel}
                    >
                        {cancelLabel}
                    </button>

                    <button
                        className={
                            variant === "danger"
                                ? "danger-button"
                                : "primary-button"
                        }
                        type="submit"
                        disabled={confirmDisabled}
                        autoFocus={!children}
                    >
                        {confirmLabel}
                    </button>
                </div>
            </form>
        </div>
    );
}


function HistoryModal({
    open,
    onClose,
}) {
    const [items, setItems] =
        useState([]);

    const [total, setTotal] =
        useState(0);

    const [loading, setLoading] =
        useState(false);

    const [error, setError] =
        useState("");

    // { type: "all" } hoặc { type: "one", id }
    const [pendingDelete, setPendingDelete] =
        useState(null);

    async function loadHistory() {
        setLoading(true);
        setError("");

        try {
            const data =
                await getHistory(100);

            setItems(
                data.items || []
            );

            setTotal(
                data.total || 0
            );
        } catch (requestError) {
            setError(
                requestError.message
            );
        } finally {
            setLoading(false);
        }
    }

    useEffect(() => {
        if (open) {
            loadHistory();
        }
    }, [open]);

    async function handleDelete(
        historyId
    ) {
        try {
            await deleteHistory(
                historyId
            );

            await loadHistory();
        } catch (requestError) {
            setError(
                requestError.message
            );
        }
    }

    async function handleClear() {
        try {
            await clearHistory();
            await loadHistory();
        } catch (requestError) {
            setError(
                requestError.message
            );
        }
    }

    async function handleConfirmDelete() {
        const target = pendingDelete;
        setPendingDelete(null);

        if (!target) {
            return;
        }

        if (target.type === "all") {
            await handleClear();
        } else {
            await handleDelete(target.id);
        }
    }

    if (!open) {
        return null;
    }

    return (
        <div
            className="modal-backdrop"
            onClick={(event) => {
                if (
                    event.target ===
                    event.currentTarget
                ) {
                    onClose();
                }
            }}
        >
            <div className="modal">
                <div className="modal-header">
                    <h2>
                        Lịch sử hỏi đáp
                    </h2>

                    <button
                        className="modal-close"
                        type="button"
                        onClick={onClose}
                    >
                        ×
                    </button>
                </div>

                <div className="history-toolbar">
                    <span>
                        {loading
                            ? "Đang tải..."
                            : `${total} lượt hỏi đáp`}
                    </span>

                    <button
                        className="clear-history-button"
                        type="button"
                        disabled={items.length === 0}
                        onClick={() =>
                            setPendingDelete({
                                type: "all",
                            })
                        }
                    >
                        Xóa toàn bộ
                    </button>
                </div>

                {error && (
                    <div className="notice error">
                        {error}
                    </div>
                )}

                <div className="history-list">
                    {!loading &&
                        items.length === 0 && (
                            <div className="history-empty">
                                Chưa có lịch sử hỏi đáp.
                            </div>
                        )}

                    {items.map((item) => (
                        <div
                            className="history-item"
                            key={item.id}
                        >
                            <div className="history-question">
                                {item.question}
                            </div>

                            <div className="history-answer">
                                {item.answer}
                            </div>

                            <div className="history-info">
                                <span>
                                    {item.created_at}
                                </span>

                                <button
                                    className="history-delete"
                                    type="button"
                                    onClick={() =>
                                        setPendingDelete({
                                            type: "one",
                                            id: item.id,
                                        })
                                    }
                                >
                                    Xóa
                                </button>
                            </div>
                        </div>
                    ))}
                </div>
            </div>

            <ConfirmDialog
                open={pendingDelete !== null}
                variant="danger"
                title={
                    pendingDelete?.type === "all"
                        ? "Xóa toàn bộ lịch sử hỏi đáp"
                        : "Xóa lượt hỏi đáp"
                }
                message={
                    pendingDelete?.type === "all"
                        ? `Toàn bộ ${total} lượt hỏi đáp sẽ bị xóa vĩnh viễn và không thể khôi phục. Bạn có chắc chắn muốn tiếp tục?`
                        : "Lượt hỏi đáp này sẽ bị xóa vĩnh viễn và không thể khôi phục. Bạn có chắc chắn muốn tiếp tục?"
                }
                confirmLabel="Xóa"
                cancelLabel="Hủy"
                onConfirm={handleConfirmDelete}
                onCancel={() => setPendingDelete(null)}
            />
        </div>
    );
}


function SystemTestModal({
    open,
    onClose,
}) {
    const [suite, setSuite] =
        useState("regression");

    const [result, setResult] =
        useState(null);

    const [loading, setLoading] =
        useState(false);

    const [error, setError] =
        useState("");

    const [keyDialogOpen, setKeyDialogOpen] =
        useState(false);

    const [keyInput, setKeyInput] =
        useState("");

    function handleRunTests() {
        if (!getAdminKey()) {
            setKeyInput("");
            setKeyDialogOpen(true);
            return;
        }

        executeTests();
    }

    function handleSubmitKey() {
        setAdminKey(keyInput.trim());
        setKeyDialogOpen(false);
        executeTests();
    }

    async function executeTests() {
        setLoading(true);
        setError("");
        setResult(null);

        try {
            const data =
                await runSystemTests(
                    suite
                );

            setResult(data);
        } catch (requestError) {
            setError(
                requestError.message
            );
        } finally {
            setLoading(false);
        }
    }

    if (!open) {
        return null;
    }

    const passed =
        result?.status === "PASS";

    return (
        <div
            className="modal-backdrop"
            onClick={(event) => {
                if (
                    event.target ===
                    event.currentTarget
                ) {
                    onClose();
                }
            }}
        >
            <div className="test-modal">
                <div className="modal-header">
                    <div>
                        <h2>
                            🧪 Kiểm thử CivicBot –
                            Chương 5
                        </h2>

                        <p className="modal-subtitle">
                            Unit → Integration →
                            System → Acceptance →
                            Regression
                        </p>
                    </div>

                    <button
                        className="modal-close"
                        type="button"
                        onClick={onClose}
                    >
                        ×
                    </button>
                </div>

                <div className="test-toolbar">
                    <label htmlFor="test-suite">
                        Bộ kiểm thử
                    </label>

                    <select
                        id="test-suite"
                        value={suite}
                        onChange={(event) =>
                            setSuite(
                                event.target.value
                            )
                        }
                    >
                        <option value="quick">
                            Kiểm thử nhanh
                        </option>

                        <option value="ui">
                            Kiểm thử giao diện
                        </option>

                        <option value="regression">
                            Kiểm thử hồi quy
                        </option>

                        <option value="all">
                            Chạy tất cả
                        </option>
                    </select>

                    <button
                        className="primary-button"
                        type="button"
                        disabled={loading}
                        onClick={
                            handleRunTests
                        }
                    >
                        {loading
                            ? "⏳ Đang kiểm thử..."
                            : "▶ Chạy kiểm thử"}
                    </button>
                </div>

                <div
                    className={
                        `test-summary ${
                            result
                                ? passed
                                    ? "pass"
                                    : "fail"
                                : ""
                        }`
                    }
                >
                    {loading &&
                        "Đang chạy bộ kiểm thử..."}

                    {!loading &&
                        !result &&
                        !error &&
                        "Chưa chạy kiểm thử."}

                    {!loading &&
                        result &&
                        `${
                            passed
                                ? "✓ PASS"
                                : "✗ FAIL"
                        } — Tổng: ${
                            result.total || 0
                        } | Đạt: ${
                            result.passed || 0
                        } | Lỗi: ${
                            result.failed || 0
                        } | Pass rate: ${
                            result.pass_rate || 0
                        }%`}
                </div>

                <div className="test-note">
                    Bộ kiểm thử nội bộ không gọi
                    Gemini và không tiêu tốn API quota.
                </div>

                {error && (
                    <div className="notice error">
                        {error}
                    </div>
                )}

                <div className="test-results">
                    {result?.results?.map(
                        (item) => (
                            <div
                                key={
                                    item.test_id
                                }
                                className={
                                    `test-card ${
                                        item.status ===
                                        "PASS"
                                            ? "pass"
                                            : "fail"
                                    }`
                                }
                            >
                                <h3>
                                    {item.status ===
                                    "PASS"
                                        ? "✓"
                                        : "✗"}{" "}
                                    {item.test_id} —{" "}
                                    {item.layer}
                                </h3>

                                <div className="test-card-name">
                                    {item.name}
                                </div>

                                <div className="test-card-time">
                                    Thời gian:{" "}
                                    {item.duration_ms} ms
                                </div>

                                <div className="test-card-detail">
                                    <strong>
                                        Mong đợi:
                                    </strong>{" "}
                                    {item.expected}

                                    <br />

                                    <strong>
                                        Thực tế:
                                    </strong>{" "}
                                    {item.actual}

                                    <br />

                                    {item.detail}
                                </div>
                            </div>
                        )
                    )}
                </div>
            </div>

            <ConfirmDialog
                open={keyDialogOpen}
                title="Xác thực quyền quản trị"
                message="Chức năng chạy kiểm thử chỉ dành cho quản trị viên. Vui lòng nhập khóa quản trị (ADMIN_API_KEY) đã cấu hình trong tệp .env."
                confirmLabel="Xác nhận"
                cancelLabel="Hủy"
                confirmDisabled={!keyInput.trim()}
                onConfirm={handleSubmitKey}
                onCancel={() => setKeyDialogOpen(false)}
            >
                <input
                    className="confirm-input"
                    type="password"
                    autoComplete="off"
                    autoFocus
                    placeholder="Nhập khóa quản trị"
                    value={keyInput}
                    onChange={(event) =>
                        setKeyInput(event.target.value)
                    }
                />

                <p className="confirm-hint">
                    Khóa chỉ được lưu tạm trong phiên làm việc hiện tại và tự xóa khi đóng thẻ trình duyệt.
                </p>
            </ConfirmDialog>
        </div>
    );
}


function App() {
    const [messages, setMessages] =
        useState([
            initialMessage,
        ]);

    const [question, setQuestion] =
        useState("");

    const [selectedFile, setSelectedFile] =
        useState(null);

    const [loading, setLoading] =
        useState(false);

    const [historyOpen, setHistoryOpen] =
        useState(false);

    const [testsOpen, setTestsOpen] =
        useState(false);

    const [status, setStatus] =
        useState({
            backend: "Đang kiểm tra...",
            database: "Đang kiểm tra...",
            gemini: "Đang kiểm tra...",
        });

    const [statusMessage, setStatusMessage] =
        useState("");

    const messagesEndRef =
        useRef(null);

    useEffect(() => {
        messagesEndRef.current?.scrollIntoView(
            {
                behavior: "smooth",
            }
        );
    }, [messages, loading]);

    useEffect(() => {
        loadStatus();
    }, []);

    async function loadStatus() {
        try {
            const data =
                await getSystemStatus();

            setStatus({
                backend:
                    data.backend === "ok"
                        ? "OK"
                        : data.backend || "Lỗi",
                database:
                    data.database === "ok"
                        ? "OK"
                        : data.database || "Lỗi",
                gemini:
                    data.gemini ===
                    "configured"
                        ? "Đã cấu hình"
                        : data.gemini || "Thiếu cấu hình",
            });
        } catch (requestError) {
            setStatus({
                backend: "Lỗi kết nối",
                database: "Không kiểm tra được",
                gemini: "Không kiểm tra được",
            });

            setStatusMessage(
                requestError.message
            );
        }
    }

    async function handleCheckGemini() {
        setStatusMessage(
            "Đang kiểm tra Gemini..."
        );

        try {
            const data =
                await checkGemini();

            setStatusMessage(
                data.message ||
                    (
                        data.ok
                            ? "Gemini đang hoạt động."
                            : "Gemini chưa hoạt động."
                    )
            );

            setStatus((current) => ({
                ...current,
                gemini: data.ok
                    ? "Hoạt động"
                    : "Không hoạt động",
            }));
        } catch (requestError) {
            setStatusMessage(
                requestError.message
            );
        }
    }

    function handleSuggestion(
        suggestion
    ) {
        setQuestion(
            suggestion
        );
    }

    function handleFileChange(event) {
        const file =
            event.target.files?.[0] ||
            null;

        setSelectedFile(file);
    }

    function removeSelectedFile() {
        setSelectedFile(null);
    }

    async function handleSubmit(event) {
        event.preventDefault();

        const trimmedQuestion =
            question.trim();

        if (
            !trimmedQuestion &&
            !selectedFile
        ) {
            setStatusMessage(
                "Bạn hãy nhập câu hỏi hoặc chọn tệp đính kèm."
            );

            return;
        }

        const userMessage = {
            role: "user",
            blocks: [
                {
                    content:
                        trimmedQuestion ||
                        "Phân tích tệp đính kèm",
                    source_type: "user",
                    source_label: "BẠN",
                    meta: "",
                },
            ],
            fileName:
                selectedFile?.name || "",
            sources: [],
            createdAt: new Date(),
        };

        setMessages((current) => [
            ...current,
            userMessage,
        ]);

        setQuestion("");
        setLoading(true);
        setStatusMessage("");

        try {
            const data =
                await sendChat(
                    trimmedQuestion,
                    selectedFile
                );

            const botMessage = {
                role: "bot",
                blocks:
                    data.answer_blocks || [
                        {
                            content:
                                data.answer ||
                                "Hệ thống chưa có câu trả lời.",
                            source_type: "system",
                            source_label: "HỆ THỐNG",
                            meta: "",
                        },
                    ],
                sources:
                    data.sources || [],
                createdAt: new Date(),
            };

            setMessages((current) => [
                ...current,
                botMessage,
            ]);
        } catch (requestError) {
            setMessages((current) => [
                ...current,
                {
                    role: "bot",
                    blocks: [
                        {
                            content:
                                `Không thể kết nối hệ thống: ${
                                    requestError.message
                                }`,
                            source_type: "system",
                            source_label: "HỆ THỐNG",
                            meta: "",
                        },
                    ],
                    sources: [],
                    createdAt: new Date(),
                },
            ]);
        } finally {
            setSelectedFile(null);
            setLoading(false);
        }
    }

    return (
        <div className="app">
            <header className="hero">
                <div>
                    <div className="hero-kicker">
                        CIVICBOT MODERN RAG
                    </div>

                    <h1>CivicBot</h1>

                    <p>
                        Trợ lý AI hỗ trợ tra cứu
                        thủ tục cư trú và giấy tờ
                        tùy thân.
                    </p>

                    <div className="hero-actions">
                        <button
                            type="button"
                            className="hero-button"
                            onClick={() =>
                                setTestsOpen(
                                    true
                                )
                            }
                        >
                            🧪 Kiểm thử hệ thống
                        </button>

                        <button
                            type="button"
                            className="hero-button"
                            onClick={() =>
                                setHistoryOpen(
                                    true
                                )
                            }
                        >
                            Lịch sử hỏi đáp
                        </button>
                    </div>
                </div>

                <div className="person-card">
                    <div className="person-avatar">
                        CB
                    </div>

                    <div>
                        <h2>
                            Thông tin dự án
                        </h2>

                        <p>
                            <strong>
                                Đề tài:
                            </strong>
                            <br />
                            Chatbot AI hỗ trợ tra cứu
                            thủ tục cư trú và giấy tờ
                            tùy thân
                        </p>

                        <p>
                            <strong>
                                Người thực hiện:
                            </strong>
                            <br />
                            Trần Thu Phương và
                            Lê Văn Đạt
                        </p>
                    </div>
                </div>
            </header>

            <main className="dashboard">
                <section className="chat-panel">
                    <div className="intro">
                        <h2>
                            Tra cứu nhanh thủ tục
                            hành chính
                        </h2>

                        <p>
                            Nhập câu hỏi cụ thể hoặc
                            gửi ảnh, PDF, DOCX để
                            CivicBot hỗ trợ.
                        </p>

                        <div className="intro-tags">
                            <span>
                                CSDL nội bộ ưu tiên
                            </span>

                            <span>
                                Gemini dự phòng
                            </span>

                            <span>
                                Có nguồn thủ tục
                            </span>
                        </div>
                    </div>

                    <div className="messages">
                        {messages.map(
                            (
                                message,
                                index
                            ) => (
                                <ChatMessage
                                    key={index}
                                    message={message}
                                />
                            )
                        )}

                        {messages.length === 1 && (
                            <div className="suggestions">
                                {suggestions.map(
                                    (item) => (
                                        <button
                                            key={
                                                item.value
                                            }
                                            type="button"
                                            className="suggestion"
                                            onClick={() =>
                                                handleSuggestion(
                                                    item.value
                                                )
                                            }
                                        >
                                            {item.text}
                                        </button>
                                    )
                                )}
                            </div>
                        )}

                        {loading && (
                            <div className="typing">
                                CivicBot đang xử lý...
                            </div>
                        )}

                        <div
                            ref={messagesEndRef}
                        />
                    </div>

                    {selectedFile && (
                        <div className="file-preview">
                            <span>
                                📎{" "}
                                {selectedFile.name}
                            </span>

                            <button
                                type="button"
                                onClick={
                                    removeSelectedFile
                                }
                            >
                                Xóa
                            </button>
                        </div>
                    )}

                    <form
                        className="composer"
                        onSubmit={
                            handleSubmit
                        }
                    >
                        <label
                            className="attach-button"
                            title="Đính kèm tệp"
                        >
                            📎

                            <input
                                type="file"
                                accept="image/*,.pdf,.doc,.docx"
                                onChange={
                                    handleFileChange
                                }
                            />
                        </label>

                        <textarea
                            value={question}
                            onChange={(event) =>
                                setQuestion(
                                    event.target.value
                                )
                            }
                            onKeyDown={(event) => {
                                if (
                                    event.key ===
                                        "Enter" &&
                                    !event.shiftKey
                                ) {
                                    event.preventDefault();
                                    handleSubmit(
                                        event
                                    );
                                }
                            }}
                            placeholder="Nhập câu hỏi của bạn..."
                            rows="1"
                        />

                        <button
                            className="send-button"
                            type="submit"
                            disabled={loading}
                        >
                            Gửi
                        </button>
                    </form>
                </section>

                <aside className="side-panel">
                    <h2>
                        Thông tin vận hành
                    </h2>

                    <h3>
                        Logic xử lý
                    </h3>

                    <div className="logic-list">
                        <div>
                            1. Tiếp nhận câu hỏi
                            hoặc tệp đính kèm
                        </div>

                        <div>
                            2. Tìm kiếm trong
                            CSDL nội bộ
                        </div>

                        <div>
                            3. Có dữ liệu →
                            trả lời nội bộ
                        </div>

                        <div>
                            4. Chưa có dữ liệu →
                            gọi Gemini
                        </div>

                        <div>
                            5. Hiển thị nguồn
                            thủ tục
                        </div>

                        <div>
                            6. Trả kết quả đúng
                            trọng tâm
                        </div>
                    </div>

                    <h3>
                        Người thực hiện
                    </h3>

                    <div className="person-detail">
                        <strong>
                            Họ và tên:
                        </strong>
                        <br />
                        Trần Thu Phương và
                        Lê Văn Đạt
                        <br />

                        <strong>
                            Đề tài:
                        </strong>{" "}
                        CivicBot
                        <br />

                        <strong>
                            Phạm vi:
                        </strong>{" "}
                        Thủ tục cư trú và giấy tờ
                        tùy thân
                    </div>

                    <h3>
                        Trạng thái hệ thống
                    </h3>

                    <div className="status-card">
                        <div className="status-row">
                            <span>
                                Backend
                            </span>

                            <strong>
                                {status.backend}
                            </strong>
                        </div>

                        <div className="status-row">
                            <span>
                                Cơ sở dữ liệu
                            </span>

                            <strong>
                                {status.database}
                            </strong>
                        </div>

                        <div className="status-row">
                            <span>
                                Gemini API
                            </span>

                            <strong>
                                {status.gemini}
                            </strong>
                        </div>

                        <button
                            className="check-button"
                            type="button"
                            onClick={
                                handleCheckGemini
                            }
                        >
                            Kiểm tra Gemini
                        </button>

                        {statusMessage && (
                            <div className="status-message">
                                {statusMessage}
                            </div>
                        )}
                    </div>
                </aside>
            </main>

            <HistoryModal
                open={historyOpen}
                onClose={() =>
                    setHistoryOpen(false)
                }
            />

            <SystemTestModal
                open={testsOpen}
                onClose={() =>
                    setTestsOpen(false)
                }
            />
        </div>
    );
}


export default App;