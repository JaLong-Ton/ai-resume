"""
AI Resume Analysis System - Flask Backend.

Parses PDF resumes, extracts structured info via LLM, and computes
job-description match scores. Designed for Alibaba Cloud FC Python runtime.

Replaced FastAPI with Flask for native WSGI support on FC.
"""

import httpx
import json
import os
import re
import time

import pymupdf
from flask import Flask, jsonify, request

# ---------------------------------------------------------------------------
# Configuration (from environment)
# ---------------------------------------------------------------------------

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
LLM_TIMEOUT = 60  # seconds
LLM_MAX_RETRIES = 3

# ---------------------------------------------------------------------------
# Flask application
# ---------------------------------------------------------------------------

app = Flask(__name__)


@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "*"
    return response

# ---------------------------------------------------------------------------
# DeepSeek LLM client
# ---------------------------------------------------------------------------

_http_client: httpx.Client | None = None


def _get_http_client() -> httpx.Client:
    global _http_client
    if _http_client is None:
        _http_client = httpx.Client(timeout=LLM_TIMEOUT)
    return _http_client


# ---------------------------------------------------------------------------
# PDF parsing
# ---------------------------------------------------------------------------


def extract_pdf_text(file_bytes: bytes) -> str:
    text_parts: list[str] = []
    with pymupdf.open(stream=file_bytes, filetype="pdf") as doc:
        for page in doc:
            page_text = page.get_text()
            if page_text.strip():
                text_parts.append(page_text)
    return "\n\n".join(text_parts)


def clean_resume_text(raw_text: str) -> str:
    text = re.sub(r"[ \t]+", " ", raw_text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[^\S\n]{2,}", " ", text)
    return text.strip()


# ---------------------------------------------------------------------------
# LLM prompts
# ---------------------------------------------------------------------------

EXTRACTION_SYSTEM_PROMPT = """你是一个专业的简历信息提取专家。从给定的简历文本中提取以下信息，并以严格的JSON格式返回。

必须提取的字段：
{
  "name": "候选人姓名",
  "phone": "联系电话（纯数字字符串）",
  "email": "电子邮箱地址",
  "address": "地址信息（城市/地区级别即可）",
  "job_intention": "求职意向/期望岗位（从简历中推断，没有则为null）",
  "expected_salary": "期望薪资（没有则为null）",
  "work_years": 工作年限整数（根据工作经历推算，没有则为0）,
  "education": {
    "level": "学历层次：博士/硕士/本科/大专/高中",
    "school": "毕业院校名称",
    "major": "专业名称",
    "graduation_date": "毕业时间"
  },
  "skills": ["技术或职业技能列表"],
  "project_experience": [
    {
      "name": "项目名称",
      "role": "担任角色",
      "description": "项目简要描述（1-2句话）",
      "technologies": ["项目中使用的主要技术"]
    }
  ]
}

规则：
1. 只返回JSON对象，不要包含任何其他文字或标记
2. 无法提取的字段设为 null 或空数组
3. 电话号码只保留数字部分
4. 地址信息提取到城市/地区级别即可
5. 工作年限根据简历中的工作经历时间跨度推算
6. 项目经验最多提取5个最重要的"""

MATCHING_SYSTEM_PROMPT = """你是一个专业的简历匹配分析专家。根据候选人信息和岗位描述，计算匹配度评分并给出详细分析。

以严格JSON格式返回：
{
  "job_keywords": ["从岗位描述中提取的关键技能或技术要求"],
  "match_score": 0.85,
  "skill_match_rate": 0.80,
  "experience_relevance": 0.70,
  "education_match": true,
  "overall_feedback": "总体评价（用中文，2-3句话）",
  "strengths": ["优势1", "优势2", "优势3"],
  "weaknesses": ["不足1", "不足2"]
}

评分规则：
- 技能匹配率 = 候选人具备的岗位相关技能数 / 岗位描述中的关键技能总数
- 经验相关性：根据工作经历与岗位的关联程度评分（0.0-1.0）
- 学历匹配：学历满足或超出要求为true，否则为false；岗位未明确学历要求则为true
- 综合匹配分数 = 0.5 × 技能匹配率 + 0.3 × 经验相关性 + 0.2 × (学历匹配 ? 1.0 : 0.5)
- 所有分数保留2位小数

只返回JSON对象，不要包含任何其他文字。"""


# ---------------------------------------------------------------------------
# LLM call helpers
# ---------------------------------------------------------------------------


def _call_llm(system_prompt: str, user_prompt: str) -> dict:
    client = _get_http_client()
    for attempt in range(LLM_MAX_RETRIES):
        try:
            resp = client.post(
                f"{DEEPSEEK_BASE_URL}/v1/chat/completions",
                headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}"},
                json={
                    "model": DEEPSEEK_MODEL,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 8192,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            if not content:
                raise RuntimeError("LLM returned empty response")
            return json.loads(content)
        except (httpx.HTTPStatusError, httpx.RequestError, KeyError, json.JSONDecodeError) as e:
            if attempt == LLM_MAX_RETRIES - 1:
                raise RuntimeError(f"LLM call failed: {e}")


def build_result(raw_text: str, job_description: str = "") -> dict:
    """Common pipeline: parse text -> extract info -> optionally match."""
    data = {
        "parsed_text": raw_text[:5000],
        "extracted_info": _extract_from_llm(raw_text),
        "matching": None,
    }
    if job_description.strip():
        data["matching"] = _match_from_llm(data["extracted_info"], job_description.strip())
    return data


def _extract_from_llm(text: str) -> dict:
    raw = _call_llm(EXTRACTION_SYSTEM_PROMPT, f"请从以下简历文本中提取信息：\n\n{text}")
    education = raw.get("education") or {}
    return {
        "name": raw.get("name"),
        "phone": raw.get("phone"),
        "email": raw.get("email"),
        "address": raw.get("address"),
        "job_intention": raw.get("job_intention"),
        "expected_salary": raw.get("expected_salary"),
        "work_years": raw.get("work_years", 0) or 0,
        "education": {
            "level": education.get("level"),
            "school": education.get("school"),
            "major": education.get("major"),
            "graduation_date": education.get("graduation_date"),
        },
        "skills": raw.get("skills") or [],
        "project_experience": [
            {
                "name": (p or {}).get("name"),
                "role": (p or {}).get("role"),
                "description": (p or {}).get("description"),
                "technologies": (p or {}).get("technologies") or [],
            }
            for p in raw.get("project_experience") or []
        ],
    }


def _match_from_llm(extracted_info: dict, job_description: str) -> dict:
    candidate_json = json.dumps(extracted_info, ensure_ascii=False, indent=2)
    raw = _call_llm(
        MATCHING_SYSTEM_PROMPT,
        f"## 候选人信息\n{candidate_json}\n\n## 岗位描述\n{job_description}\n\n请计算匹配度。",
    )
    return {
        "job_keywords": raw.get("job_keywords") or [],
        "match_score": raw.get("match_score", 0.0) or 0.0,
        "skill_match_rate": raw.get("skill_match_rate", 0.0) or 0.0,
        "experience_relevance": raw.get("experience_relevance", 0.0) or 0.0,
        "education_match": raw.get("education_match", True),
        "overall_feedback": raw.get("overall_feedback", "") or "",
        "strengths": raw.get("strengths") or [],
        "weaknesses": raw.get("weaknesses") or [],
    }


def _read_file(file) -> tuple[bytes, str]:
    """Validate and read uploaded file. Returns (bytes, filename)."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise ValueError("Only PDF files are supported")
    data = file.read()
    if len(data) > MAX_FILE_SIZE:
        raise ValueError("File size exceeds 10MB limit")
    if not data:
        raise ValueError("File is empty")
    return data, file.filename


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------


@app.route("/health")
def health():
    return jsonify({"status": "ok", "version": "1.0.0"})


@app.route("/api/upload", methods=["POST"])
def upload_resume():
    """Upload and parse a PDF resume, extract info. No matching."""
    if "file" not in request.files:
        return jsonify({"success": False, "error": {"message": "No file provided"}}), 400

    try:
        file_bytes, filename = _read_file(request.files["file"])
    except ValueError as e:
        return jsonify({"success": False, "error": {"message": str(e)}}), 400

    t0 = time.time()
    raw_text = extract_pdf_text(file_bytes)
    if not raw_text.strip():
        return jsonify({"success": False, "error": {"message": "No text extracted from PDF"}}), 400

    cleaned = clean_resume_text(raw_text)

    try:
        extracted = _extract_from_llm(cleaned)
    except Exception as e:
        return jsonify({"success": False, "error": {"message": f"LLM extraction failed: {e}"}}), 502

    return jsonify({
        "success": True,
        "data": {
            "file_name": filename,
            "parsed_text": cleaned[:5000],
            "extracted_info": extracted,
            "processing_time_ms": int((time.time() - t0) * 1000),
        },
    })


@app.route("/api/analyze", methods=["POST"])
def analyze_resume():
    """Upload a PDF resume, extract info, and optionally match against a job description."""
    if "file" not in request.files:
        return jsonify({"success": False, "error": {"message": "No file provided"}}), 400

    try:
        file_bytes, filename = _read_file(request.files["file"])
    except ValueError as e:
        return jsonify({"success": False, "error": {"message": str(e)}}), 400

    t0 = time.time()
    raw_text = extract_pdf_text(file_bytes)
    if not raw_text.strip():
        return jsonify({"success": False, "error": {"message": "No text extracted from PDF"}}), 400

    cleaned = clean_resume_text(raw_text)

    try:
        extracted = _extract_from_llm(cleaned)
    except Exception as e:
        return jsonify({"success": False, "error": {"message": f"LLM extraction failed: {e}"}}), 502

    matching = None
    job_description = request.form.get("job_description", "").strip()
    if job_description:
        try:
            matching = _match_from_llm(extracted, job_description)
        except Exception as e:
            return jsonify({"success": False, "error": {"message": f"LLM matching failed: {e}"}}), 502

    return jsonify({
        "success": True,
        "data": {
            "file_name": filename,
            "parsed_text": cleaned[:5000],
            "extracted_info": extracted,
            "matching": matching,
            "processing_time_ms": int((time.time() - t0) * 1000),
        },
    })


# ---------------------------------------------------------------------------
# WSGI handler for FC Python runtime (HTTP trigger)
# ---------------------------------------------------------------------------

# FC Python runtime HTTP trigger expects the handler to be a WSGI callable.
# Flask's `app` is already WSGI-compatible. Expose it at module level.
handler = app


# ---------------------------------------------------------------------------
# Entry point for local development
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
