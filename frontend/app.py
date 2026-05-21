from __future__ import annotations

import os
from typing import Any

import requests
import streamlit as st


API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
EXAMPLE_QUERIES = [
    "For Pulsar N160, what is the spark plug gap?",
    "My TVS Sport will not start because I left the stand down. What should I do?",
    "My Splendor feels weak and is not picking up speed properly.",
    "How can I modify my bike to make it faster?",
]


st.set_page_config(page_title="Bike Troubleshooting Assistant", layout="wide")

st.markdown(
    """
    <style>
    .block-container { padding-top: 2rem; }
    .small-muted { color: #6b7280; font-size: 0.9rem; }
    .status-card {
        border: 1px solid #e5e7eb;
        border-radius: 0.75rem;
        padding: 0.85rem 1rem;
        background: #ffffff;
    }
    .citation-card {
        border-left: 4px solid #2563eb;
        padding: 0.6rem 0 0.6rem 0.9rem;
        margin-bottom: 0.8rem;
        background: #f8fafc;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def parse_error(response: requests.Response) -> tuple[str, str | None]:
    try:
        detail = response.json().get("detail")
    except ValueError:
        return "Something went wrong. Please try again.", None
    if isinstance(detail, dict):
        return (
            detail.get("message") or "Something went wrong. Please try again.",
            detail.get("code"),
        )
    if isinstance(detail, str):
        return detail, None
    return "Something went wrong. Please try again.", None


def request_api(method: str, path: str, **kwargs: Any) -> tuple[dict | None, str | None, str | None]:
    try:
        response = requests.request(method, f"{API_BASE_URL}{path}", **kwargs)
    except requests.Timeout:
        return None, "The request took too long. Please try again in a moment.", "timeout"
    except requests.ConnectionError:
        return None, "I cannot reach the backend server. Please make sure it is running.", "connection_error"
    except requests.RequestException:
        return None, "The request failed. Please try again.", "request_failed"

    if not response.ok:
        message, code = parse_error(response)
        return None, message, code
    try:
        return response.json(), None, None
    except ValueError:
        return None, "The backend returned an unreadable response. Please try again.", "bad_response"


def ensure_session() -> str:
    if "session_id" not in st.session_state:
        payload, error, _ = request_api("POST", "/sessions", timeout=30)
        if error or not payload:
            st.error(error or "Could not create a session.")
            st.stop()
        st.session_state.session_id = payload["session_id"]
    return st.session_state.session_id


def reset_frontend_session() -> None:
    for key in [
        "session_id",
        "indexed_manuals",
        "chunks_indexed",
        "pages_processed",
        "last_upload_warnings",
        "voice_transcript",
        "issue_query",
    ]:
        st.session_state.pop(key, None)


def indexed_manuals() -> list[str]:
    return list(st.session_state.get("indexed_manuals", []))


def manuals_ready() -> bool:
    return bool(indexed_manuals()) and int(st.session_state.get("chunks_indexed", 0)) > 0


def format_size(num_bytes: int) -> str:
    mb = num_bytes / (1024 * 1024)
    return f"{mb:.1f} MB"


def set_example(query: str) -> None:
    st.session_state.issue_query = query


session_id = ensure_session()

st.title("Bike Troubleshooting Assistant")
st.caption("Grounded troubleshooting from uploaded bike manuals. If the manuals do not support an answer, the assistant refuses or asks for clarification.")

status_cols = st.columns(4)
with status_cols[0]:
    st.metric("Manual status", "Ready" if manuals_ready() else "Waiting")
with status_cols[1]:
    st.metric("Manuals", len(indexed_manuals()))
with status_cols[2]:
    st.metric("Chunks", st.session_state.get("chunks_indexed", 0))
with status_cols[3]:
    st.metric("Session", f"{session_id[:8]}…")

with st.sidebar:
    st.subheader("1. Upload manuals")
    manuals = st.file_uploader(
        "Owner manual, service manual, or user guide",
        type=["pdf"],
        accept_multiple_files=True,
        help="PDFs are processed for this backend session only; they are not saved as durable app data.",
    )

    if manuals:
        total_size = sum(manual.size for manual in manuals)
        st.caption(f"Selected: {len(manuals)} PDF(s), {format_size(total_size)} total")
        with st.expander("Selected files", expanded=False):
            for manual in manuals:
                st.write(f"- {manual.name} · {format_size(manual.size)}")

    process_clicked = st.button(
        "Process manuals",
        use_container_width=True,
        disabled=not manuals,
        help="Upload at least one PDF to enable processing.",
    )
    if process_clicked and manuals:
        files = [("files", (manual.name, manual.getvalue(), "application/pdf")) for manual in manuals]
        with st.spinner("Extracting text, running OCR if needed, and building the retrieval index..."):
            payload, error, _ = request_api(
                "POST",
                f"/sessions/{session_id}/manuals",
                files=files,
                timeout=240,
            )
        if error or not payload:
            st.error(error or "Upload failed.")
        else:
            st.session_state.indexed_manuals = payload.get("documents", [])
            st.session_state.chunks_indexed = payload.get("chunks_indexed", 0)
            st.session_state.pages_processed = payload.get("pages_processed", 0)
            st.session_state.last_upload_warnings = payload.get("warnings", [])
            st.success(
                f"Ready: indexed {payload['chunks_indexed']} chunks from "
                f"{payload['pages_processed']} pages."
            )

    if manuals_ready():
        st.success("Manual index is ready for questions.")
        with st.expander("Indexed manuals", expanded=False):
            for name in indexed_manuals():
                st.write(f"- {name}")
        for warning in st.session_state.get("last_upload_warnings", []):
            st.warning(warning)
    else:
        st.info("Upload and process manuals before asking troubleshooting questions.")

    st.divider()
    st.subheader("Session behavior")
    st.caption(
        "Manuals stay in backend memory for this session only. Image input is used only to extract visible observations; manuals remain the diagnostic source."
    )
    if st.button("Start fresh session", use_container_width=True):
        reset_frontend_session()
        st.rerun()

main_left, main_right = st.columns([0.62, 0.38], gap="large")

with main_left:
    st.subheader("2. Describe the issue")
    if not manuals_ready():
        st.warning("Manuals are not indexed yet. You can draft a question, but asking is disabled until upload processing is complete.")

    input_tab, voice_tab, image_tab = st.tabs(["Text", "Voice", "Image"])

    with input_tab:
        if "issue_query" not in st.session_state:
            st.session_state.issue_query = st.session_state.get("voice_transcript", "")
        st.text_area(
            "Question",
            placeholder="Example: My bike jerks while accelerating.",
            key="issue_query",
            height=135,
        )
        st.caption("Tip: include the bike model if multiple manuals are uploaded, e.g. “For Pulsar NS160...”")

    with voice_tab:
        audio = st.file_uploader(
            "Upload a voice note",
            type=["wav", "mp3", "m4a", "aac", "ogg", "flac", "webm"],
        )
        if audio and st.button("Transcribe voice note", use_container_width=True):
            with st.spinner("Transcribing..."):
                payload, error, _ = request_api(
                    "POST",
                    "/transcribe",
                    files={"file": (audio.name, audio.getvalue(), audio.type)},
                    timeout=150,
                )
            if error or not payload:
                st.error(error or "Transcription failed.")
            else:
                st.session_state.voice_transcript = payload["transcript"]
                st.session_state.issue_query = st.session_state.voice_transcript
                st.success("Transcript added to the question box.")
                st.write(payload["transcript"])

    with image_tab:
        image = st.file_uploader(
            "Optional image",
            type=["png", "jpg", "jpeg", "webp"],
            help="Use images only to capture observable facts such as warning lights, smoke, leaks, or visible text.",
        )
        if image:
            st.image(image, caption="Image selected for observation-only analysis", use_container_width=True)
        st.caption("The vision model observes. The manuals diagnose.")

    st.markdown("#### Try a sample")
    example_cols = st.columns(2)
    for index, example in enumerate(EXAMPLE_QUERIES):
        with example_cols[index % 2]:
            st.button(
                example,
                key=f"example_{index}",
                on_click=set_example,
                args=(example,),
                use_container_width=True,
            )

    ask_disabled = not manuals_ready() or not st.session_state.get("issue_query", "").strip()
    ask_help = None
    if not manuals_ready():
        ask_help = "Process at least one manual before asking."
    elif not st.session_state.get("issue_query", "").strip():
        ask_help = "Describe the issue first."

    ask_clicked = st.button(
        "Ask from manuals",
        type="primary",
        use_container_width=True,
        disabled=ask_disabled,
        help=ask_help,
    )

with main_right:
    st.subheader("How the guardrail works")
    st.markdown(
        """
        1. Understand the issue and ambiguity.
        2. Retrieve relevant manual excerpts.
        3. Answer only if evidence is strong enough.
        4. Cite exact manual text.
        5. Refuse or ask questions when unsupported.
        """
    )
    st.info("Reliability beats coverage: a refusal is a valid safe outcome.")


def render_observations(payload: dict) -> None:
    if payload.get("vision_warning"):
        st.warning(payload["vision_warning"])

    observation = payload.get("vision_observation")
    if not observation:
        return
    with st.expander("Image observations used for retrieval", expanded=True):
        columns = st.columns(2)
        with columns[0]:
            if observation.get("visible_observations"):
                st.markdown("**Visible observations**")
                for item in observation["visible_observations"]:
                    st.write(f"- {item}")
            if observation.get("visible_components"):
                st.markdown("**Visible components**")
                for item in observation["visible_components"]:
                    st.write(f"- {item}")
        with columns[1]:
            if observation.get("visible_text"):
                st.markdown("**Visible text**")
                for item in observation["visible_text"]:
                    st.write(f"- {item}")
            if observation.get("uncertainties"):
                st.markdown("**Uncertainties**")
                for item in observation["uncertainties"]:
                    st.write(f"- {item}")

    if payload.get("enriched_query"):
        with st.expander("Retrieval trace: enriched query", expanded=False):
            st.code(payload["enriched_query"])


def render_result(payload: dict) -> None:
    st.divider()
    st.subheader("Result")
    render_observations(payload)

    status = payload.get("status")
    confidence = payload.get("confidence_level", "low")
    confidence_score = payload.get("confidence_score", 0)

    status_cols = st.columns(3)
    with status_cols[0]:
        st.metric("Status", str(status).replace("_", " ").title())
    with status_cols[1]:
        st.metric("Confidence", str(confidence).title(), f"{confidence_score:.2f}")
    with status_cols[2]:
        st.metric("Citations", len(payload.get("citations", [])))

    if status == "clarification_needed":
        st.info("I need a bit more detail before searching or answering confidently.")
        for question in payload.get("clarification_questions", []):
            st.write(f"- {question}")
        return

    if status == "low_confidence":
        st.warning(payload.get("message") or "I could not find enough manual support to answer confidently.")
        for question in payload.get("clarification_questions", []):
            st.write(f"- {question}")
        return

    st.markdown("### Answer")
    st.markdown("**Issue summary**")
    st.write(payload.get("issue_summary") or "No issue summary returned.")
    st.markdown("**Possible cause**")
    st.write(payload.get("possible_cause") or "No supported possible cause returned.")
    st.markdown("**Recommended action**")
    st.write(payload.get("recommended_action") or "No supported action returned.")

    if payload.get("safety_warning"):
        st.error(payload["safety_warning"])
    if payload.get("escalation_recommendation"):
        st.info(payload["escalation_recommendation"])

    citations = payload.get("citations", [])
    if citations:
        st.markdown("### Manual references")
        for number, citation in enumerate(citations, start=1):
            st.markdown(
                f"""
                <div class="citation-card">
                  <strong>[{number}] {citation['document_name']}</strong><br/>
                  Pages {citation['page_start']}-{citation['page_end']} · {citation['section_title']}
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.blockquote(citation["excerpt"])
    else:
        st.warning("No citation was returned. Treat this as unsupported.")


if ask_clicked:
    query = st.session_state.get("issue_query", "")
    with st.spinner("Retrieving manual evidence and checking grounding..."):
        if image:
            payload, error, code = request_api(
                "POST",
                "/troubleshoot/image",
                data={"session_id": session_id, "query": query},
                files={"image": (image.name, image.getvalue(), image.type)},
                timeout=210,
            )
        else:
            payload, error, code = request_api(
                "POST",
                "/troubleshoot",
                json={"session_id": session_id, "query": query},
                timeout=150,
            )
    if error or not payload:
        if code == "manuals_not_indexed":
            st.session_state.indexed_manuals = []
            st.session_state.chunks_indexed = 0
        st.error(error or "Request failed.")
    else:
        render_result(payload)
