from __future__ import annotations

import io
import os
import random
import re
import textwrap
import zipfile
from dataclasses import dataclass
from pathlib import Path

import pdfplumber
import streamlit as st
from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
ANSWER_MODEL = "llama-3.3-70b-versatile"
PARSER_MODEL = "llama-3.3-70b-versatile"

PAGE_W = 900
PAGE_H = 1180
MARGIN_L = 96
MARGIN_TOP = 104
MARGIN_BOTTOM = 72
LINE_SPACING = 36
RULED_COLOR = "#c8d8e8"
MARGIN_LINE = "#ef9f9f"
PAPER_BG = "#fbf7f0"
INK_COLOR = "#162544"
HEAD_COLOR = "#13263a"

HANDWRITING_FONT_CANDIDATES = [
    "C:/Windows/Fonts/segoesc.ttf",
    "C:/Windows/Fonts/seguisli.ttf",
    "C:/Windows/Fonts/Gabriola.ttf",
    "/usr/share/fonts/truetype/google-fonts/Lora-Italic-Variable.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationSerif-Italic.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSerifItalic.ttf",
]

DISPLAY_FONT_CANDIDATES = [
    "C:/Windows/Fonts/georgiab.ttf",
    "C:/Windows/Fonts/timesbd.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationSerif-Bold.ttf",
]

QUESTION_LINE_RE = re.compile(r"^\s*(?:question\s*)?(?:q\s*)?(\d{1,3})[\)\].:\-]\s*(.+)$", re.IGNORECASE)


@dataclass(frozen=True)
class GenerationSettings:
    api_key: str
    subject: str
    detail: str
    tone: str
    max_questions: int


def configure_page() -> None:
    st.set_page_config(page_title="HandwriteAI Studio", layout="wide")


def inject_styles() -> None:
    st.markdown(
        """
        <style>
          @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400..900;1,400..900&family=Plus+Jakarta+Sans:ital,wght@0,200..800;1,200..800&display=swap');

          :root {
            --paper: #f8f2e8;
            --paper-strong: #fffdf9;
            --ink: #111e30;
            --muted: #4e5d6c;
            --accent: #c04938;
            --accent-soft: #f8e7e1;
            --line: #dfd0c0;
            --success: #215a3a;
          }

          .stApp {
            background:
              radial-gradient(circle at top left, rgba(192, 73, 56, 0.08), transparent 32%),
              radial-gradient(circle at top right, rgba(20, 38, 58, 0.08), transparent 30%),
              radial-gradient(circle at bottom center, rgba(192, 73, 56, 0.03), transparent 40%),
              linear-gradient(180deg, #f8f2e7 0%, #f1e7d7 100%);
            color: var(--ink);
          }

          html, body, [class*="css"] {
            font-family: 'Plus Jakarta Sans', sans-serif !important;
          }

          h1, h2, h3 {
            font-family: 'Playfair Display', Georgia, serif !important;
            color: var(--ink);
            letter-spacing: -0.02em;
            font-weight: 700 !important;
          }

          [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #0e1b29 0%, #1a3045 100%);
            border-right: 1px solid rgba(255,255,255,0.06);
          }

          [data-testid="stSidebar"] * {
            color: #fbf9f6 !important;
          }

          [data-testid="stSidebar"] input,
          [data-testid="stSidebar"] textarea,
          [data-testid="stSidebar"] select {
            background: rgba(255,255,255,0.06) !important;
            border: 1px solid rgba(255,255,255,0.12) !important;
            border-radius: 12px !important;
            color: #fbf9f6 !important;
          }

          .hero {
            background: linear-gradient(135deg, rgba(255, 255, 255, 0.85) 0%, rgba(249, 244, 235, 0.5) 100%);
            backdrop-filter: blur(20px);
            -webkit-backdrop-filter: blur(20px);
            border: 1px solid rgba(255, 255, 255, 0.7);
            border-radius: 28px;
            padding: 2.4rem;
            box-shadow: 0 24px 60px rgba(19, 38, 58, 0.05);
            margin-bottom: 1.8rem;
            position: relative;
            overflow: hidden;
          }

          .hero::before {
            content: "";
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 5px;
            background: linear-gradient(90deg, var(--accent) 0%, #14263a 100%);
          }

          .hero-kicker {
            display: inline-block;
            font-size: 0.82rem;
            text-transform: uppercase;
            letter-spacing: 0.22em;
            color: var(--accent);
            margin-bottom: 0.8rem;
            font-weight: 700;
          }

          .hero-copy {
            max-width: 58rem;
            color: var(--muted);
            line-height: 1.6;
            font-size: 1.05rem;
          }

          .stat-card, .panel-card {
            background: rgba(255, 255, 255, 0.45);
            backdrop-filter: blur(20px) saturate(180%);
            -webkit-backdrop-filter: blur(20px) saturate(180%);
            border: 1px solid rgba(255, 255, 255, 0.6);
            border-radius: 22px;
            box-shadow: 0 16px 40px rgba(19, 38, 58, 0.04);
            transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
          }

          .stat-card:hover, .panel-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 24px 50px rgba(19, 38, 58, 0.08);
            border-color: rgba(192, 73, 56, 0.2);
          }

          .stat-card {
            padding: 1.2rem 1.4rem;
            min-height: 120px;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
          }

          .stat-label {
            color: var(--muted);
            font-size: 0.82rem;
            text-transform: uppercase;
            letter-spacing: 0.16em;
            font-weight: 700;
          }

          .stat-value {
            font-family: 'Playfair Display', Georgia, serif;
            font-size: 2.2rem;
            color: var(--ink);
            margin-top: 0.15rem;
            font-weight: 700;
          }

          .stat-note {
            color: var(--muted);
            font-size: 0.88rem;
            margin-top: 0.2rem;
          }

          .panel-card {
            padding: 1.8rem;
          }

          .stButton > button,
          .stDownloadButton > button {
            border-radius: 999px;
            border: none;
            background: linear-gradient(135deg, #d35241 0%, #c04938 50%, #9e3627 100%);
            color: #fff !important;
            padding: 0.8rem 1.8rem;
            font-weight: 600;
            letter-spacing: 0.03em;
            transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
            box-shadow: 0 10px 30px rgba(192, 73, 56, 0.2);
          }

          .stButton > button:hover,
          .stDownloadButton > button:hover {
            transform: translateY(-2px);
            box-shadow: 0 16px 40px rgba(192, 73, 56, 0.3);
            filter: brightness(1.08);
          }

          .stTabs [data-baseweb="tab-list"] {
            gap: 0.8rem;
            background: rgba(255, 255, 255, 0.25);
            padding: 0.4rem;
            border-radius: 999px;
            border: 1px solid rgba(19, 38, 58, 0.05);
            max-width: fit-content;
            margin-bottom: 1.5rem;
          }

          .stTabs [data-baseweb="tab"] {
            background: transparent !important;
            border-radius: 999px;
            padding: 0.6rem 1.4rem !important;
            border: none !important;
            font-weight: 600 !important;
            color: var(--muted) !important;
            transition: all 0.2s ease !important;
          }

          .stTabs [data-baseweb="tab"][aria-selected="true"] {
            background: linear-gradient(135deg, #0e1b29 0%, #1a3045 100%) !important;
            color: #ffffff !important;
            box-shadow: 0 8px 24px rgba(14, 27, 41, 0.2);
          }

          .caption-strip {
            color: var(--muted);
            font-size: 0.95rem;
            padding-top: 0.4rem;
            border-top: 1px solid rgba(19, 38, 58, 0.05);
            margin-top: 0.8rem;
          }
        </style>
        """,
        unsafe_allow_html=True,
    )


def init_state() -> None:
    if "session_initialized" not in st.session_state:
        st.session_state.clear()
        st.session_state["session_initialized"] = True

    defaults = {
        "questions_editor": "",
        "raw_text": "",
        "question_source": "None",
        "generated_pages": [],
        "generated_answers": [],
        "zip_bytes": b"",
        "combined_png": b"",
        "last_file_name": "",
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def reset_generated_content() -> None:
    st.session_state.generated_pages = []
    st.session_state.generated_answers = []
    st.session_state.zip_bytes = b""
    st.session_state.combined_png = b""


def reset_workspace() -> None:
    st.session_state.questions_editor = ""
    st.session_state.raw_text = ""
    st.session_state.question_source = "None"
    st.session_state.last_file_name = ""
    reset_generated_content()


def groq_client(api_key: str) -> OpenAI:
    return OpenAI(api_key=api_key, base_url=GROQ_BASE_URL)


@st.cache_data(show_spinner=False)
def extract_text_from_pdf(file_bytes: bytes) -> str:
    chunks: list[str] = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            chunks.append(page.extract_text() or "")
    return "\n".join(chunks).strip()


def clean_question(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"^\s*(?:question\s*)?(?:q\s*)?\d{1,3}[\)\].:\-]\s*", "", text, flags=re.IGNORECASE)
    return text.strip(" -")


def dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        key = item.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def questions_to_editor_text(questions: list[str]) -> str:
    return "\n".join(f"{idx}. {question}" for idx, question in enumerate(questions, start=1))


def parse_editor_questions(text: str) -> list[str]:
    questions: list[str] = []
    for raw_line in text.splitlines():
        line = clean_question(raw_line)
        if line:
            questions.append(line)
    return dedupe_preserve_order(questions)


def heuristic_extract_questions(raw_text: str, max_questions: int) -> list[str]:
    normalized_lines = [re.sub(r"\s+", " ", line).strip() for line in raw_text.splitlines()]
    questions: list[str] = []
    current: list[str] = []

    for line in normalized_lines:
        match = QUESTION_LINE_RE.match(line)
        if match:
            if current:
                questions.append(clean_question(" ".join(current)))
            current = [match.group(2)]
            continue

        if current and line:
            current.append(line)

    if current:
        questions.append(clean_question(" ".join(current)))

    if not questions:
        paragraphs = [
            clean_question(block)
            for block in re.split(r"\n\s*\n", raw_text)
            if clean_question(block)
        ]
        questions = [block for block in paragraphs if "?" in block or len(block.split()) > 7]

    return dedupe_preserve_order([question for question in questions if question])[:max_questions]


def parse_questions_with_model(raw_text: str, client: OpenAI, max_questions: int) -> list[str]:
    prompt = (
        "The following text came from an exam or worksheet PDF.\n"
        "Extract every question exactly once and return only a numbered list.\n"
        "Do not answer the questions.\n"
        "Keep each question on one line.\n\n"
        f"TEXT:\n{raw_text[:12000]}"
    )

    response = client.chat.completions.create(
        model=PARSER_MODEL,
        max_tokens=1800,
        temperature=0.1,
        messages=[{"role": "user", "content": prompt}],
    )

    content = response.choices[0].message.content or ""
    return parse_editor_questions(content)[:max_questions]


def generate_answer(question: str, client: OpenAI, settings: GenerationSettings) -> str:
    detail_guides = {
        "Brief": "Write 2 to 4 sentences.",
        "Moderate": "Write 1 to 2 short paragraphs covering the essential points.",
        "Detailed": "Write a thorough explanation with multiple concise paragraphs.",
    }

    tone_guides = {
        "Exam ready": "Write in polished exam prose with direct, confident phrasing.",
        "Simple": "Write in plain language that is easy to study and revise.",
        "Clinical": "Write with a clinical tone and precise medical terminology.",
    }

    subject_line = f"Subject area: {settings.subject}." if settings.subject else "Subject area not specified."
    user_prompt = (
        f"{subject_line}\n"
        f"{detail_guides[settings.detail]}\n"
        f"{tone_guides[settings.tone]}\n"
        "Do not use bullet points. Do not use markdown. Start directly with the answer.\n\n"
        f"Question: {question}"
    )

    response = client.chat.completions.create(
        model=ANSWER_MODEL,
        max_tokens=900,
        temperature=0.3,
        stop=["Question:", "User:", "<|im_end|>"],
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an expert medical assistant writing accurate, exam-style answers. "
                    "Be clear, concise, and organized in prose."
                ),
            },
            {"role": "user", "content": user_prompt},
        ],
    )

    answer = (response.choices[0].message.content or "").strip()
    answer = re.sub(r"^Answer:\s*", "", answer, flags=re.IGNORECASE)
    return answer.strip()


def first_existing_path(candidates: list[str]) -> str | None:
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    return None


def load_fonts(body_size: int = 28, title_size: int = 28, meta_size: int = 22) -> tuple[ImageFont.ImageFont, ImageFont.ImageFont, ImageFont.ImageFont]:
    body_path = first_existing_path(HANDWRITING_FONT_CANDIDATES)
    title_path = first_existing_path(DISPLAY_FONT_CANDIDATES)

    try:
        body_font = ImageFont.truetype(body_path, body_size) if body_path else ImageFont.load_default()
    except OSError:
        body_font = ImageFont.load_default()

    try:
        title_font = ImageFont.truetype(title_path, title_size) if title_path else ImageFont.load_default()
    except OSError:
        title_font = ImageFont.load_default()

    try:
        meta_font = ImageFont.truetype(title_path, meta_size) if title_path else ImageFont.load_default()
    except OSError:
        meta_font = ImageFont.load_default()

    return body_font, title_font, meta_font


def draw_notebook_background(draw: ImageDraw.ImageDraw) -> None:
    y = MARGIN_TOP
    while y < PAGE_H - MARGIN_BOTTOM:
        draw.line([(MARGIN_L - 12, y), (PAGE_W - 44, y)], fill=RULED_COLOR, width=1)
        y += LINE_SPACING

    draw.line(
        [(MARGIN_L - 12, MARGIN_TOP - 24), (MARGIN_L - 12, PAGE_H - MARGIN_BOTTOM + 8)],
        fill=MARGIN_LINE,
        width=2,
    )

    for index in range(6):
        center_x = 28
        center_y = int(PAGE_H * 0.12 + index * PAGE_H * 0.13)
        draw.ellipse(
            [center_x - 11, center_y - 11, center_x + 11, center_y + 11],
            outline="#b7b7b7",
            width=2,
        )


def jitter(x: float, y: float, amount: float = 1.1) -> tuple[float, float]:
    return x + random.uniform(-amount, amount), y + random.uniform(-amount, amount)


def wrap_answer_text(answer: str, width: int = 63) -> list[str]:
    lines: list[str] = []
    for block in answer.splitlines():
        stripped = block.strip()
        if not stripped:
            lines.append("")
            continue
        lines.extend(textwrap.wrap(stripped, width=width) or [""])
    return lines


def render_pages(question: str, answer: str, question_number: int) -> list[Image.Image]:
    body_font, title_font, meta_font = load_fonts()
    answer_lines = wrap_answer_text(answer)
    question_lines = textwrap.wrap(question, width=56)[:2] or [question]

    usable_height = PAGE_H - MARGIN_TOP - MARGIN_BOTTOM
    header_rows = len(question_lines) + 2
    first_page_capacity = max(10, int((usable_height - (header_rows * LINE_SPACING) - 16) / LINE_SPACING))
    later_page_capacity = max(14, int(usable_height / LINE_SPACING))

    chunks: list[list[str]] = []
    if len(answer_lines) <= first_page_capacity:
        chunks = [answer_lines]
    else:
        chunks.append(answer_lines[:first_page_capacity])
        remainder = answer_lines[first_page_capacity:]
        while remainder:
            chunks.append(remainder[:later_page_capacity])
            remainder = remainder[later_page_capacity:]

    pages: list[Image.Image] = []
    for page_index, chunk in enumerate(chunks, start=1):
        image = Image.new("RGB", (PAGE_W, PAGE_H), PAPER_BG)
        draw = ImageDraw.Draw(image)
        draw_notebook_background(draw)

        y = MARGIN_TOP
        if page_index == 1:
            draw.text(jitter(MARGIN_L, y - LINE_SPACING + 3), f"Question {question_number}", font=title_font, fill=HEAD_COLOR)
            for line in question_lines:
                draw.text((MARGIN_L + 10, y), line, font=meta_font, fill="#4d5f4a")
                y += LINE_SPACING
            draw.text(jitter(MARGIN_L, y), "Answer", font=title_font, fill=HEAD_COLOR)
            y += LINE_SPACING + 6

        for line in chunk:
            if y > PAGE_H - MARGIN_BOTTOM - LINE_SPACING:
                break
            if line.strip():
                draw.text(jitter(MARGIN_L, y - 5), line, font=body_font, fill=INK_COLOR)
            y += LINE_SPACING

        footer = f"Page {page_index}"
        draw.text((PAGE_W - 110, PAGE_H - 44), footer, font=meta_font, fill="#a5a5a5")
        pages.append(image)

    return pages


def build_zip(images: list[Image.Image]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for index, image in enumerate(images, start=1):
            file_buffer = io.BytesIO()
            image.save(file_buffer, format="PNG")
            archive.writestr(f"answer_page_{index:02d}.png", file_buffer.getvalue())
    return buffer.getvalue()


def build_combined_png(images: list[Image.Image]) -> bytes:
    canvas = Image.new("RGB", (PAGE_W, PAGE_H * len(images)), PAPER_BG)
    for index, image in enumerate(images):
        canvas.paste(image, (0, index * PAGE_H))
    buffer = io.BytesIO()
    canvas.save(buffer, format="PNG")
    return buffer.getvalue()


def sync_uploaded_file(uploaded_file: st.runtime.uploaded_file_manager.UploadedFile | None) -> None:
    current_name = uploaded_file.name if uploaded_file else ""
    if current_name != st.session_state.last_file_name:
        st.session_state.last_file_name = current_name
        st.session_state.raw_text = ""
        st.session_state.question_source = "None"
        st.session_state.questions_editor = ""
        reset_generated_content()


def render_sidebar() -> GenerationSettings:
    with st.sidebar:
        st.markdown("## Studio Settings")
        
        # Retrieve the API key securely from secrets or environment variables in the background
        api_key = ""
        try:
            if "GROQ_API_KEY" in st.secrets:
                api_key = st.secrets["GROQ_API_KEY"]
        except Exception:
            pass
        if not api_key:
            api_key = os.getenv("GROQ_API_KEY", "")
            
        st.session_state.api_key = api_key

        subject = st.text_input("Subject or topic", placeholder="Pharmacology, pathology, anatomy")
        detail = st.selectbox("Answer depth", ["Brief", "Moderate", "Detailed"], index=1)
        tone = st.selectbox("Writing style", ["Exam ready", "Simple", "Clinical"], index=0)
        max_questions = st.slider("Question limit per run", min_value=1, max_value=20, value=8)

        st.divider()
        if st.button("Reset workspace", use_container_width=True):
            reset_workspace()
            st.rerun()

        st.caption(
            "PDF extraction works locally, and question parsing can fall back to a local heuristic."
        )

    return GenerationSettings(
        api_key=api_key.strip(),
        subject=subject.strip(),
        detail=detail,
        tone=tone,
        max_questions=max_questions,
    )


def render_header(question_count: int, page_count: int, source_name: str) -> None:
    source_label = source_name if source_name else "No source loaded"
    st.markdown(
        f"""
        <div class="hero">
          <div class="hero-kicker">HandwriteAI Studio</div>
          <h1>Turn messy question sheets into polished handwritten answer packs.</h1>
          <div class="hero-copy">
            Upload a PDF, clean up the extracted questions, and generate notebook-style answer pages
            that feel ready for study, review, or submission prep.
          </div>
          <div class="caption-strip">Current source: {source_label}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col1, col2, col3 = st.columns(3)
    cards = [
        ("Questions ready", str(question_count), "Editable question list for the next run."),
        ("Rendered pages", str(page_count), "Notebook pages generated in this session."),
        ("Workflow state", "Ready" if question_count else "Waiting", "Upload a file or paste questions to begin."),
    ]

    for column, (label, value, note) in zip((col1, col2, col3), cards):
        with column:
            st.markdown(
                f"""
                <div class="stat-card">
                  <div class="stat-label">{label}</div>
                  <div class="stat-value">{value}</div>
                  <div class="stat-note">{note}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def render_source_tab(settings: GenerationSettings) -> None:
    st.markdown('<div class="panel-card">', unsafe_allow_html=True)
    
    # Elegant custom choice for input source
    input_method = st.radio(
        "Choose how you want to load your questions:",
        ["📄 Upload PDF Document", "✍️ Copy & Paste Questions Directly"],
        horizontal=True,
    )
    
    st.divider()

    if input_method == "📄 Upload PDF Document":
        uploaded = st.file_uploader("Upload a PDF question paper", type=["pdf"])
        sync_uploaded_file(uploaded)

        parse_clicked = st.button("Extract questions from PDF", use_container_width=True, disabled=uploaded is None)
        if parse_clicked and uploaded is not None:
            reset_generated_content()
            pdf_bytes = uploaded.getvalue()

            with st.spinner("Reading the PDF and collecting questions..."):
                raw_text = extract_text_from_pdf(pdf_bytes)
                st.session_state.raw_text = raw_text

                if not raw_text:
                    st.error("No selectable text was found in that PDF.")
                else:
                    questions: list[str]
                    source_label: str
                    if settings.api_key:
                        client = groq_client(settings.api_key)
                        try:
                            questions = parse_questions_with_model(raw_text, client, settings.max_questions)
                            source_label = "Model parser"
                        except Exception as exc:
                            st.warning(f"Model-based parsing failed, so a local fallback was used. Details: {exc}")
                            questions = heuristic_extract_questions(raw_text, settings.max_questions)
                            source_label = "Local fallback parser"
                    else:
                        questions = heuristic_extract_questions(raw_text, settings.max_questions)
                        source_label = "Local parser"

                    if questions:
                        st.session_state.questions_editor = questions_to_editor_text(questions)
                        st.session_state.question_source = source_label
                        st.success(f"Loaded {len(questions)} question(s) using {source_label.lower()}.")
                        st.info("👉 **Next Step**: Click on the **'Review questions'** tab at the top of the page to review them, or go straight to the **'Generate pages'** tab to generate the answers!")
                    else:
                        st.error("No questions were detected. Paste them manually or try a clearer PDF.")

        if st.session_state.raw_text:
            with st.expander("Preview extracted PDF text", expanded=False):
                st.text_area(
                    "Raw text preview",
                    st.session_state.raw_text[:5000],
                    height=240,
                    label_visibility="collapsed",
                )
    
    else:
        # Beautiful, dedicated copy/paste text area
        manual_text = st.text_area(
            "Paste your questions here (one question per line or numbered)",
            height=300,
            placeholder="1. Define shock.\n2. List the causes of jaundice.\n3. Explain the mechanism of action of aspirin.",
        )

        if st.button("Load pasted questions", use_container_width=True):
            reset_generated_content()
            questions = parse_editor_questions(manual_text)
            if questions:
                st.session_state.questions_editor = questions_to_editor_text(questions[: settings.max_questions])
                st.session_state.question_source = "Manual input"
                st.success(f"Loaded {len(questions[: settings.max_questions])} question(s) from pasted text.")
                st.info("👉 **Next Step**: Click on the **'Review questions'** tab at the top of the page to review them, or go straight to the **'Generate pages'** tab to generate the answers!")
            else:
                st.error("No valid questions were found in the pasted text.")

    st.markdown("</div>", unsafe_allow_html=True)


def render_review_tab() -> list[str]:
    st.markdown('<div class="panel-card">', unsafe_allow_html=True)
    st.text_area(
        "Editable question list",
        key="questions_editor",
        height=320,
        placeholder="Your extracted or pasted questions will appear here.",
    )

    questions = parse_editor_questions(st.session_state.questions_editor)
    source_label = st.session_state.question_source

    col1, col2 = st.columns([0.45, 0.55])
    with col1:
        st.metric("Questions ready", len(questions))
        st.caption(f"Current source: {source_label}")

    with col2:
        if st.button("Normalize list", use_container_width=True, disabled=not st.session_state.questions_editor.strip()):
            st.session_state.questions_editor = questions_to_editor_text(questions)
            st.rerun()

    if questions:
        preview_rows = "\n".join(f"{idx}. {question}" for idx, question in enumerate(questions[:5], start=1))
        st.code(preview_rows, language="text")
        st.info("👉 **Next Step**: Click on the **'Generate pages'** tab at the top of the page, then click the **'Generate handwritten answer pack'** button to answer these questions!")
    else:
        st.info("Questions will appear here after PDF extraction or manual paste.")

    st.markdown("</div>", unsafe_allow_html=True)
    return questions


def render_generation_tab(settings: GenerationSettings, questions: list[str]) -> None:
    st.markdown('<div class="panel-card">', unsafe_allow_html=True)

    if not questions:
        st.info("Add or extract some questions first, then come back here to generate answer pages.")
        st.markdown("</div>", unsafe_allow_html=True)
        return

    if not settings.api_key:
        st.warning("Please configure your GROQ_API_KEY in Streamlit Secrets (.streamlit/secrets.toml) or as an environment variable to generate answers.")

    start_disabled = not settings.api_key
    if st.button("Generate handwritten answer pack", use_container_width=True, disabled=start_disabled):
        reset_generated_content()
        client = groq_client(settings.api_key)
        progress = st.progress(0.0)
        status = st.empty()
        answer_records: list[dict[str, str]] = []
        all_pages: list[Image.Image] = []

        for index, question in enumerate(questions, start=1):
            status.markdown(f"Generating answer {index} of {len(questions)}")
            try:
                answer = generate_answer(question, client, settings)
                pages = render_pages(question, answer, index)
                answer_records.append({"question": question, "answer": answer})
                all_pages.extend(pages)
            except Exception as exc:
                answer_records.append({"question": question, "answer": f"Generation failed: {exc}"})
            progress.progress(index / len(questions))

        status.empty()
        progress.empty()

        successful_pages = [page for page in all_pages]
        st.session_state.generated_pages = successful_pages
        st.session_state.generated_answers = answer_records

        if successful_pages:
            st.session_state.zip_bytes = build_zip(successful_pages)
            st.session_state.combined_png = build_combined_png(successful_pages)
            st.success(f"Generated {len(successful_pages)} page(s) across {len(answer_records)} answer(s).")
        else:
            st.error("The run completed, but no notebook pages were rendered.")

    pages = st.session_state.generated_pages
    answers = st.session_state.generated_answers

    if pages:
        st.divider()
        st.subheader("Preview")
        preview_columns = st.columns(min(3, len(pages)))
        for index, image in enumerate(pages[:6]):
            with preview_columns[index % len(preview_columns)]:
                st.image(image, use_container_width=True, caption=f"Page {index + 1}")

        st.divider()
        download_left, download_right = st.columns(2)
        with download_left:
            st.download_button(
                "Download ZIP of pages",
                data=st.session_state.zip_bytes,
                file_name="handwritten_answers.zip",
                mime="application/zip",
                use_container_width=True,
            )
        with download_right:
            st.download_button(
                "Download combined PNG",
                data=st.session_state.combined_png,
                file_name="handwritten_answers_combined.png",
                mime="image/png",
                use_container_width=True,
            )

        st.divider()
        st.subheader("Generated answers")
        for index, record in enumerate(answers, start=1):
            with st.expander(f"Question {index}: {textwrap.shorten(record['question'], width=90, placeholder='...')}"):
                st.write(record["answer"])

    st.markdown("</div>", unsafe_allow_html=True)


def main() -> None:
    configure_page()
    inject_styles()
    init_state()
    settings = render_sidebar()

    current_questions = parse_editor_questions(st.session_state.questions_editor)
    render_header(
        question_count=len(current_questions),
        page_count=len(st.session_state.generated_pages),
        source_name=st.session_state.last_file_name,
    )

    tabs = st.tabs(["Prepare source", "Review questions", "Generate pages"])

    with tabs[0]:
        render_source_tab(settings)

    with tabs[1]:
        current_questions = render_review_tab()

    with tabs[2]:
        render_generation_tab(settings, current_questions)


if __name__ == "__main__":
    main()
