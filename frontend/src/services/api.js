const API_BASE_URL =
    import.meta.env.VITE_API_BASE_URL ||
    "http://127.0.0.1:8000";


// Mỗi trình duyệt có một session_id riêng để tách lịch sử hội thoại
// và cho phép backend hiểu câu hỏi nối tiếp.
const SESSION_KEY = "civicbot_session_id";

function createSessionId() {
    if (window.crypto && window.crypto.randomUUID) {
        return window.crypto.randomUUID();
    }

    return `s-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function getSessionId() {
    let sessionId = localStorage.getItem(SESSION_KEY);

    if (!sessionId) {
        sessionId = createSessionId();
        localStorage.setItem(SESSION_KEY, sessionId);
    }

    return sessionId;
}

export function resetSession() {
    localStorage.removeItem(SESSION_KEY);
    return getSessionId();
}


// Khóa quản trị chỉ lưu trong sessionStorage (mất khi đóng tab),
// không ghi cứng trong mã nguồn.
const ADMIN_KEY = "civicbot_admin_key";

export function getAdminKey() {
    return sessionStorage.getItem(ADMIN_KEY) || "";
}

export function setAdminKey(key) {
    if (key) {
        sessionStorage.setItem(ADMIN_KEY, key);
    } else {
        sessionStorage.removeItem(ADMIN_KEY);
    }
}


export async function sendChat(
    question,
    file = null
) {
    const formData = new FormData();

    formData.append(
        "question",
        question || ""
    );

    formData.append(
        "session_id",
        getSessionId()
    );

    if (file) {
        formData.append(
            "file",
            file
        );
    }

    const response = await fetch(
        `${API_BASE_URL}/api/chat`,
        {
            method: "POST",
            body: formData,
        }
    );

    if (!response.ok) {
        const errorText =
            await response.text();

        throw new Error(
            errorText ||
            "Không thể gửi câu hỏi."
        );
    }

    return response.json();
}


export async function getHistory(
    limit = 100
) {
    const response = await fetch(
        `${API_BASE_URL}/api/history?limit=${limit}&session_id=${encodeURIComponent(getSessionId())}`
    );

    if (!response.ok) {
        throw new Error(
            "Không thể tải lịch sử hỏi đáp."
        );
    }

    return response.json();
}


export async function clearHistory() {
    const response = await fetch(
        `${API_BASE_URL}/api/history?session_id=${encodeURIComponent(getSessionId())}`,
        {
            method: "DELETE",
        }
    );

    if (!response.ok) {
        throw new Error(
            "Không thể xóa lịch sử hỏi đáp."
        );
    }

    return response.json();
}


export async function deleteHistory(
    historyId
) {
    const response = await fetch(
        `${API_BASE_URL}/api/history/${historyId}?session_id=${encodeURIComponent(getSessionId())}`,
        {
            method: "DELETE",
        }
    );

    if (!response.ok) {
        throw new Error(
            "Không thể xóa bản ghi lịch sử."
        );
    }

    return response.json();
}


export async function getSystemStatus() {
    const response = await fetch(
        `${API_BASE_URL}/api/status`
    );

    if (!response.ok) {
        throw new Error(
            "Không thể kiểm tra trạng thái hệ thống."
        );
    }

    return response.json();
}


export async function checkGemini() {
    const response = await fetch(
        `${API_BASE_URL}/api/check-gemini`
    );

    if (!response.ok) {
        throw new Error(
            "Không thể kiểm tra Gemini."
        );
    }

    return response.json();
}


export async function runSystemTests(
    suite = "regression"
) {
    const response = await fetch(
        `${API_BASE_URL}/api/system-tests/run`,
        {
            method: "POST",
            headers: {
                "Content-Type":
                    "application/json",
                "Accept":
                    "application/json",
                "X-Admin-Key":
                    getAdminKey(),
            },
            body: JSON.stringify({
                suite,
            }),
        }
    );

    if (response.status === 401 || response.status === 403) {
        sessionStorage.removeItem(ADMIN_KEY);
        throw new Error(
            "Khóa quản trị không đúng hoặc chưa nhập."
        );
    }

    if (!response.ok) {
        const errorText =
            await response.text();

        throw new Error(
            errorText ||
            "Không thể chạy kiểm thử."
        );
    }

    return response.json();
}


export {
    API_BASE_URL,
};