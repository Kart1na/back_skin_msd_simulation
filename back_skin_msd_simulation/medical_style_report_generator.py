"""Generate a medical-style smart massage detection report.

The report is a formal A4 "检测报告单" layout generated with HTML/CSS and
optionally exported to PDF through Playwright. It does not replace the legacy
ReportLab or modern product-style report generators.
"""

from __future__ import annotations

import argparse
import json
import os
import warnings
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import requests
except ImportError:  # pragma: no cover - optional dependency.
    requests = None

try:
    from jinja2 import Environment, FileSystemLoader, select_autoescape
except ImportError:  # pragma: no cover - optional dependency.
    Environment = None
    FileSystemLoader = None
    select_autoescape = None

try:
    import config
except ImportError:  # pragma: no cover - supports direct execution nearby.
    class _FallbackConfig:
        output_dir = str(Path(__file__).resolve().parent / "outputs")

    config = _FallbackConfig()

try:
    from pressure_recommender import recommend_pressure
except Exception:  # pragma: no cover - optional project integration.
    recommend_pressure = None


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = Path(getattr(config, "output_dir", BASE_DIR / "outputs"))
TEMPLATE_DIR = BASE_DIR / "templates"

SECTION_ORDER = ["Upper Back", "Mid Back", "Lower Back"]
SECTION_CN = {
    "Upper Back": "上背部",
    "Mid Back": "中背部",
    "Lower Back": "下背部",
}
SECTION_ADVICE = {
    "Upper Back": "拉伸放松",
    "Mid Back": "姿势维护",
    "Lower Back": "重点放松",
}
SECTION_REGION = {
    "Upper Back": "upper_back",
    "Mid Back": "mid_back",
    "Lower Back": "lower_back",
    "Spine Center": "spine_center",
}
ATTENTION_WEIGHT = {"high": 3, "attention": 2, "normal": 1}


def file_url(path: str | os.PathLike[str] | None) -> str | None:
    """Return a file:// URL for an existing path."""
    if not path:
        return None
    return Path(path).resolve().as_uri()


def as_float(value: Any, default: float = 0.0) -> float:
    """Convert a value to float with a safe default."""
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def fmt_num(value: Any, digits: int = 2) -> str:
    """Format a numeric value for customer-facing report tables."""
    if value is None:
        return "--"
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "--"


def read_json(path: Path) -> dict[str, Any] | None:
    """Read UTF-8 JSON and return None when the file is missing."""
    if not path.is_file():
        return None
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_alignment_summary(user_id: str, output_dir: str | os.PathLike[str] = "outputs") -> dict[str, Any] | None:
    """Load outputs/{user_id}_spatial_temporal_alignment.json when present."""
    output_path = resolve_output_dir(output_dir)
    return read_json(output_path / f"{user_id}_spatial_temporal_alignment.json")


def load_stiffness_stats(user_id: str, output_dir: str | os.PathLike[str] = "outputs") -> dict[str, Any] | None:
    """Load outputs/{user_id}_stiffness_stats.json when present."""
    output_path = resolve_output_dir(output_dir)
    return read_json(output_path / f"{user_id}_stiffness_stats.json")


def resolve_output_dir(output_dir: str | os.PathLike[str]) -> Path:
    """Resolve output directories consistently on Windows and Linux."""
    path = Path(output_dir)
    if str(output_dir) == "outputs":
        return DEFAULT_OUTPUT_DIR
    if path.is_absolute():
        return path
    return BASE_DIR / path


def demo_alignment() -> dict[str, Any]:
    """Return demo data when no alignment or stiffness files exist."""
    return {
        "overall": {
            "total_samples": 160,
            "contact_samples": 128,
            "contact_ratio": 0.8,
            "contact_duration_s": 6.4,
            "mean_contact_force_N": 7.8,
            "max_contact_force_N": 13.2,
        },
        "by_acupoint": [
            {"name": "肾俞", "section": "Lower Back", "region": "lower_back", "duration_s": 0.8, "contact_count": 16, "mean_force_N": 10.1, "max_force_N": 13.2, "recommended_force_N": 9.5, "attention_level": "attention"},
            {"name": "大肠俞", "section": "Lower Back", "region": "lower_back", "duration_s": 0.6, "contact_count": 12, "mean_force_N": 9.3, "max_force_N": 12.6, "recommended_force_N": 9.0, "attention_level": "normal"},
            {"name": "膈俞", "section": "Mid Back", "region": "mid_back", "duration_s": 0.5, "contact_count": 10, "mean_force_N": 7.9, "max_force_N": 10.8, "recommended_force_N": 8.5, "attention_level": "normal"},
            {"name": "风门", "section": "Upper Back", "region": "upper_back", "duration_s": 0.4, "contact_count": 8, "mean_force_N": 6.5, "max_force_N": 9.6, "recommended_force_N": 7.5, "attention_level": "normal"},
            {"name": "肺俞", "section": "Upper Back", "region": "upper_back", "duration_s": 0.4, "contact_count": 8, "mean_force_N": 6.1, "max_force_N": 8.9, "recommended_force_N": 7.5, "attention_level": "normal"},
        ],
        "by_section": [
            {"section": "Upper Back", "duration_s": 1.8, "mean_force_N": 6.4, "max_force_N": 10.2, "grade": "B"},
            {"section": "Mid Back", "duration_s": 2.2, "mean_force_N": 7.5, "max_force_N": 12.1, "grade": "B"},
            {"section": "Lower Back", "duration_s": 2.4, "mean_force_N": 10.8, "max_force_N": 13.2, "grade": "C"},
        ],
        "by_region": [],
        "aligned_records": [],
    }


def grade_from_force(mean_force: Any) -> str:
    """Grade a section from mean force."""
    value = as_float(mean_force)
    if value < 5:
        return "A"
    if value < 10:
        return "B"
    if value < 15:
        return "C"
    return "D"


def score_to_grade(score: int) -> str:
    """Convert composite score to A/B/C/D."""
    if score >= 90:
        return "A"
    if score >= 75:
        return "B"
    if score >= 60:
        return "C"
    return "D"


def attention_text(level: str | None) -> str:
    """Convert attention levels to Chinese display text."""
    return {"normal": "正常", "attention": "需关注", "high": "高关注"}.get(str(level or "normal"), "正常")


def local_recommended_force(user_id: str, section: str, region_name: str | None = None) -> float:
    """Recommend force from project recommender when possible, otherwise use local rules."""
    region_key = region_name or SECTION_REGION.get(section) or "mid_back"
    if recommend_pressure is not None:
        try:
            result = recommend_pressure(user_id, region_key)
            return as_float(result.get("recommended_force_N"))
        except Exception:
            pass
    if "spine_center" in str(region_key).lower() or section == "Spine Center":
        return 0.0
    if section == "Upper Back":
        return 8.0
    if section == "Mid Back":
        return 9.0
    if section == "Lower Back":
        return 9.0
    return 8.0


def force_status(actual_mean: Any, recommended: Any) -> str:
    """Return force suitability status."""
    actual = as_float(actual_mean)
    rec = as_float(recommended)
    if actual > rec + 2:
        return "偏高"
    if actual < rec - 3:
        return "偏低"
    return "合适"


def top_acupoints_from_source(source: dict[str, Any]) -> list[dict[str, Any]]:
    """Return TOP 5 acupoints sorted by attention and coverage."""
    if source.get("by_acupoint"):
        items = source.get("by_acupoint", [])
        rows = [
            {
                "name": item.get("name", "--"),
                "section": item.get("section", "--"),
                "region": item.get("region", "--"),
                "duration_s": as_float(item.get("duration_s")),
                "contact_count": as_float(item.get("contact_count")),
                "mean_force_N": item.get("mean_force_N"),
                "max_force_N": item.get("max_force_N"),
                "recommended_force_N": item.get("recommended_force_N"),
                "attention_level": item.get("attention_level") or "normal",
                "attention_text": attention_text(item.get("attention_level")),
            }
            for item in items
        ]
    else:
        rows = [
            {
                "name": item.get("point_id", "--"),
                "section": item.get("section", "--"),
                "region": item.get("region", "--"),
                "duration_s": 0.0,
                "contact_count": as_float(item.get("sample_count")),
                "mean_force_N": item.get("mean_force_N"),
                "max_force_N": item.get("max_force_N"),
                "recommended_force_N": None,
                "attention_level": "normal",
                "attention_text": "正常",
            }
            for item in source.get("points", [])
        ]
    rows.sort(key=lambda row: (ATTENTION_WEIGHT.get(row["attention_level"], 1), row["duration_s"], row["contact_count"]), reverse=True)
    return rows[:5]


def build_force_recommendation_rows(user_id: str, top_acupoints: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build actual/recommended force rows for important acupoints."""
    rows = []
    for item in top_acupoints:
        recommended = item.get("recommended_force_N")
        if recommended is None:
            recommended = local_recommended_force(user_id, item.get("section", ""), item.get("region"))
        rows.append({
            "name": item["name"],
            "mean_force": fmt_num(item.get("mean_force_N"), 2),
            "max_force": fmt_num(item.get("max_force_N"), 2),
            "recommended_force": fmt_num(recommended, 2),
            "status": force_status(item.get("mean_force_N"), recommended),
        })
    return rows


def build_section_rows(source: dict[str, Any]) -> list[dict[str, Any]]:
    """Build Upper/Mid/Lower section scoring rows."""
    by_section = {item.get("section"): item for item in source.get("by_section", [])}
    stiffness_sections = {item.get("section"): item for item in source.get("sections", [])}
    rows = []
    for section in SECTION_ORDER:
        item = dict(by_section.get(section) or stiffness_sections.get(section) or {})
        mean_force = item.get("mean_force_N")
        if mean_force is None and item.get("mean_stiffness_N_m") is not None:
            mean_force = as_float(item.get("mean_stiffness_N_m")) / 550.0
        grade = item.get("grade") or grade_from_force(mean_force)
        rows.append({
            "section": section,
            "section_cn": SECTION_CN[section],
            "grade": grade,
            "mean_force": fmt_num(mean_force, 2),
            "duration_s": fmt_num(item.get("duration_s"), 2),
            "advice": SECTION_ADVICE[section],
            "main_acupoints": item.get("main_acupoints") or [],
        })
    return rows


def build_score_table(source: dict[str, Any], section_rows: list[dict[str, Any]], top_acupoints: list[dict[str, Any]]) -> dict[str, Any]:
    """Build the composite score table from force, coverage, and risk signals."""
    overall = source.get("overall", {})
    contact_ratio = as_float(overall.get("contact_ratio"))
    mean_force = as_float(overall.get("mean_contact_force_N") or overall.get("mean_force_N"))
    max_force = as_float(overall.get("max_contact_force_N") or overall.get("max_force_N"))
    high_attention_count = sum(1 for item in top_acupoints if item.get("attention_level") == "high")
    high_risk = any(
        "spine_center" in str(item.get("section", "")).lower()
        or "spine_center" in str(item.get("region", "")).lower()
        or "high risk" in str(item.get("region", "")).lower()
        or item.get("attention_level") == "high"
        for item in source.get("by_acupoint", []) + source.get("by_region", [])
    )
    score = 100
    if max_force >= 15:
        score -= 10
    score -= min(20, high_attention_count * 5)
    if contact_ratio < 0.6:
        score -= 10
    if high_risk:
        score -= 15
    if mean_force < 3:
        score -= 5
    score = max(0, min(100, score))
    focus = section_rows[0]
    grade_rank = {"A": 1, "B": 2, "C": 3, "D": 4}
    focus = max(section_rows, key=lambda row: (grade_rank.get(row["grade"], 1), as_float(row["duration_s"])))
    return {
        "overall_grade": score_to_grade(score),
        "contact_ratio": f"{contact_ratio * 100:.0f}%",
        "mean_force": fmt_num(mean_force, 2),
        "max_force": fmt_num(max_force, 2),
        "focus_region": f"{focus['section']} / {focus['section_cn']}",
        "risk_tip": "需关注" if high_risk else "未见明显高风险接触",
        "score": score,
        "has_high_force": max_force >= 15,
        "has_high_risk": high_risk,
    }


def call_deepseek_api(prompt: str, api_key: str | None = None, model: str = "deepseek-chat") -> str | None:
    """Call DeepSeek OpenAI-compatible API and return generated content."""
    key = api_key or os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        return None
    if requests is None:
        warnings.warn("requests is not installed; using local report text.")
        return None
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是一个智能按摩检测报告分析助手，输出中文、客户可读、不构成医疗诊断。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.4,
    }
    try:
        response = requests.post(
            "https://api.deepseek.com/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        warnings.warn(f"DeepSeek request failed, using local fallback: {exc}")
        return None


def conclusion_prompt(context: dict[str, Any]) -> str:
    """Build DeepSeek prompt for conclusion text."""
    summary = {
        "用户编号": context["user_id"],
        "按摩部位": context["department"],
        "总采样点数": context["overall_metrics"].get("total_samples"),
        "有效接触比例": context["score_table"]["contact_ratio"],
        "平均按压力": context["score_table"]["mean_force"],
        "最大按压力": context["score_table"]["max_force"],
        "TOP5穴位": [item["name"] for item in context["top_acupoints"]],
        "区域评分": context["section_rows"],
        "高风险区域": context["score_table"]["has_high_risk"],
        "高力度接触": context["score_table"]["has_high_force"],
        "综合评分": context["score_table"]["score"],
    }
    return (
        "请基于以下智能按摩检测摘要生成检测结论。要求中文、面向普通客户、不使用医学诊断语气，"
        "不要说患有、疾病、病变，使用提示、建议关注、可能存在紧张、按摩覆盖较充分等表达，100到180字。\n"
        + json.dumps(summary, ensure_ascii=False)
    )


def recommendation_prompt(context: dict[str, Any]) -> str:
    """Build DeepSeek prompt for recommendation text."""
    summary = {
        "重点区域": context["score_table"]["focus_region"],
        "平均按压力": context["score_table"]["mean_force"],
        "最大按压力": context["score_table"]["max_force"],
        "风险提示": context["score_table"]["risk_tip"],
        "区域评分": context["section_rows"],
    }
    return (
        "请为后续智能按摩生成检测建议。必须包含下次重点按摩区域、建议起始力度范围、避让区域、按摩顺序、拉伸护理建议。"
        "使用客户能看懂的话，不要医疗诊断，120到220字。\n"
        + json.dumps(summary, ensure_ascii=False)
    )


def local_conclusion(context: dict[str, Any]) -> str:
    """Generate local fallback conclusion."""
    score = context["score_table"]
    return (
        f"本次智能按摩主要覆盖背部多个穴位区域，有效接触比例为 {score['contact_ratio']}，"
        f"平均按压力为 {score['mean_force']} N，整体力度处于较平稳范围。检测结果提示 "
        f"{score['focus_region']} 区域相对需要关注，建议后续结合舒适度反馈进行渐进式按摩调整。"
    )


def local_recommendation(context: dict[str, Any]) -> str:
    """Generate local fallback recommendation."""
    main_region = context["score_table"]["focus_region"]
    return (
        f"建议下次优先关注 {main_region}，采用低到中等力度开始，并根据用户舒适度逐步增加。"
        "脊柱中线及未知区域应保持避让。按摩顺序可从上背部热身开始，再过渡到中背部和下背部重点区域。"
        "按摩后建议进行肩胛放松、胸椎伸展和腰背拉伸，以帮助维持放松效果。"
    )


def generate_conclusion_with_deepseek(report_context: dict[str, Any], api_key: str | None = None) -> str:
    """Generate conclusion via DeepSeek or local fallback."""
    return call_deepseek_api(conclusion_prompt(report_context), api_key=api_key) or local_conclusion(report_context)


def generate_recommendation_with_deepseek(report_context: dict[str, Any], api_key: str | None = None) -> str:
    """Generate recommendation via DeepSeek or local fallback."""
    return call_deepseek_api(recommendation_prompt(report_context), api_key=api_key) or local_recommendation(report_context)


def load_report_context(
    user_id: str,
    report_id: str | None = None,
    logo_path: str | None = None,
    output_dir: str | os.PathLike[str] = "outputs",
    phone: str = "--",
    gender: str = "--",
    age: str = "--",
    department: str = "背部",
    massage_part: str = "背部",
    deepseek_api_key: str | None = None,
) -> dict[str, Any]:
    """Load all report data and return a unified template context."""
    output_path = resolve_output_dir(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    alignment = load_alignment_summary(user_id, output_path)
    stiffness = load_stiffness_stats(user_id, output_path)
    source = alignment or stiffness or demo_alignment()
    top_acupoints = top_acupoints_from_source(source)
    section_rows = build_section_rows(source)
    score_table = build_score_table(source, section_rows, top_acupoints)
    context = {
        "user_id": user_id,
        "report_id": report_id or f"DEMO-{datetime.now().year}-001",
        "created_at": datetime.now().strftime("%Y-%m-%d"),
        "department": department or massage_part,
        "massage_part": massage_part,
        "phone": phone,
        "gender": gender,
        "age": age,
        "device": "Lscure 智能按摩系统",
        "data_source": "机械臂轨迹 + 穴位 3D 点云 + 按压力数据" if alignment else "刚度统计数据 / Demo 数据",
        "logo_url": file_url(logo_path) if logo_path and Path(logo_path).is_file() else None,
        "css_url": file_url(TEMPLATE_DIR / "medical_style_massage_report.css"),
        "alignment": alignment,
        "stiffness": stiffness,
        "overall_metrics": source.get("overall", {}),
        "top_acupoints": top_acupoints,
        "force_recommendation_rows": build_force_recommendation_rows(user_id, top_acupoints),
        "section_rows": section_rows,
        "score_table": score_table,
        "trajectory_xy_url": file_url(output_path / f"{user_id}_trajectory_acupoints_xy.png") if (output_path / f"{user_id}_trajectory_acupoints_xy.png").is_file() else None,
        "output_dir": output_path,
    }
    context["conclusion"] = generate_conclusion_with_deepseek(context, api_key=deepseek_api_key)
    context["recommendation"] = generate_recommendation_with_deepseek(context, api_key=deepseek_api_key)
    return context


def render_html_report(context: dict[str, Any]) -> Path:
    """Render medical-style report HTML from Jinja2 or fallback renderer."""
    output_path = Path(context["output_dir"]) / f"{context['user_id']}_medical_style_massage_report.html"
    if Environment is None:
        html = render_fallback_html(context)
        print("Jinja2 is not installed. Using built-in fallback renderer. Install with: pip install jinja2")
    else:
        env = Environment(
            loader=FileSystemLoader(str(TEMPLATE_DIR)),
            autoescape=select_autoescape(["html", "xml"]),
        )
        template = env.get_template("medical_style_massage_report.html")
        html = template.render(**context)
    output_path.write_text(html, encoding="utf-8")
    return output_path


def status_class(status: str) -> str:
    """Return CSS class for force/status labels."""
    if status in ("偏高", "高关注"):
        return "high"
    if status in ("偏低", "需关注"):
        return "attention"
    return "normal"


def render_fallback_html(context: dict[str, Any]) -> str:
    """Render a complete report without Jinja2 so HTML generation never blocks."""
    def brand() -> str:
        if context.get("logo_url"):
            return f'<img src="{context["logo_url"]}" alt="Lscure logo" />'
        return '<span>LSCURE</span>'

    def status_span(text: str, level: str | None = None) -> str:
        cls = level or status_class(text)
        return f'<span class="status {cls}">{text}</span>'

    top_rows = "".join(
        f"<tr><td>{item['name']}</td><td>{item['section']}</td><td>{fmt_num(item['duration_s'], 2)} s</td><td>{fmt_num(item['mean_force_N'], 2)} N</td><td>{item['attention_text']}</td></tr>"
        for item in context["top_acupoints"]
    )
    force_rows = "".join(
        f"<tr><td>{item['name']}</td><td>{item['mean_force']} N</td><td>{item['max_force']} N</td><td>{item['recommended_force']} N</td><td>{status_span(item['status'])}</td></tr>"
        for item in context["force_recommendation_rows"]
    )
    section_rows = "".join(
        f"<tr><td>{item['section']} / {item['section_cn']}</td><td><span class=\"grade grade-{item['grade']}\">{item['grade']}</span></td><td>{item['mean_force']} N</td><td>{item['duration_s']} s</td><td>{item['advice']}</td></tr>"
        for item in context["section_rows"]
    )
    score = context["score_table"]
    path_panel = (
        f'<img class="path-image" src="{context["trajectory_xy_url"]}" alt="按摩穴位路径图像" />'
        if context.get("trajectory_xy_url")
        else '<div class="placeholder">未检测到轨迹图，请先运行时空对齐模块</div>'
    )
    risk_check = "☑" if score["risk_tip"] == "需关注" else "☐"
    high_force_check = "☑" if score["has_high_force"] else "☐"
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>智能按摩检测报告单 - {context['user_id']}</title>
  <link rel="stylesheet" href="{context['css_url']}" />
</head>
<body>
  <div class="page report-sheet">
    <header class="report-header">
      <div class="brand-row"><div class="logo-area">{brand()}</div><div class="hospital-name">Lscure 智能按摩评估系统</div></div>
      <h1>智能按摩检测报告单</h1>
    </header>
    <section class="submit-row"><div><span>送检科室：</span><strong>{context['department']}</strong></div><div><span>送检者：</span><strong>{context['user_id']}</strong></div><div><span>操作者：</span><strong>{context['phone']}</strong></div></section>
    <div class="block-label">被检者信息</div>
    <section class="info-grid">
      <div><span>报告编号</span><strong>{context['report_id']}</strong></div><div><span>用户</span><strong>{context['user_id']}</strong></div><div><span>性别</span><strong>{context['gender']}</strong></div>
      <div><span>年龄</span><strong>{context['age']}</strong></div><div><span>检测日期</span><strong>{context['created_at']}</strong></div><div><span>按摩部位</span><strong>{context['department']}</strong></div>
      <div><span>电话号码</span><strong>{context['phone']}</strong></div><div><span>检测设备</span><strong>{context['device']}</strong></div><div><span>数据来源</span><strong>{context['data_source']}</strong></div>
    </section>
    <section class="result-section">
      <div class="section-title">检测结果</div>
      <div class="result-meta"><span>检测日期：{context['created_at']}</span><span>姓名：{context['user_id']}</span><span>性别：{context['gender']}</span></div>
      <div class="result-grid">
        <div class="panel path-panel"><div class="panel-title">按摩穴位路径图像</div><div class="chart-frame">{path_panel}</div><p>红色表示机械臂按摩轨迹，蓝色表示穴位点，绿色表示有效接触点。</p></div>
        <div class="panel stiffness-panel"><div class="panel-title">重要穴位僵硬程度表</div><table><thead><tr><th>穴位</th><th>区域</th><th>接触时长</th><th>平均力度</th><th>关注等级</th></tr></thead><tbody>{top_rows}</tbody></table></div>
        <div class="panel force-panel"><div class="panel-title">各穴位按摩力度和推荐力度表</div><table><thead><tr><th>穴位</th><th>实际平均力度(N)</th><th>最大力度(N)</th><th>推荐力度(N)</th><th>状态</th></tr></thead><tbody>{force_rows}</tbody></table></div>
        <div class="panel section-panel"><div class="panel-title">上中下三区域评分表</div><table><thead><tr><th>区域</th><th>等级</th><th>平均力度</th><th>接触时长</th><th>建议</th></tr></thead><tbody>{section_rows}</tbody></table></div>
      </div>
      <div class="score-table"><div class="panel-title">总评分表</div><table><tbody>
        <tr><th>总体等级</th><td>{score['overall_grade']}</td><th>有效接触比例</th><td>{score['contact_ratio']}</td></tr>
        <tr><th>平均按压力</th><td>{score['mean_force']} N</td><th>最大按压力</th><td>{score['max_force']} N</td></tr>
        <tr><th>重点关注区域</th><td>{score['focus_region']}</td><th>高风险提示</th><td>{score['risk_tip']}</td></tr>
        <tr><th>综合评分</th><td colspan="3"><strong class="score-num">{score['score']}</strong> 分</td></tr>
      </tbody></table></div>
    </section>
    <section class="conclusion-section"><div class="section-title">检测结论</div><div class="checkbox-grid"><label><i>☑</i> 综合评分 {score['score']} 分，等级 {score['overall_grade']}</label><label><i>☑</i> 有效接触比例 {score['contact_ratio']}</label><label><i>{risk_check}</i> 高风险提示：{score['risk_tip']}</label><label><i>{high_force_check}</i> 存在局部较高力度接触</label></div><p>{context['conclusion']}</p></section>
    <section class="suggestion-section"><div class="section-title">检测建议</div><p>{context['recommendation']}</p></section>
    <footer>本报告为项目演示生成，仅用于研究与功能展示，不构成医疗建议。</footer>
  </div>
</body>
</html>
"""


def export_pdf_with_playwright(html_path: str | os.PathLike[str], pdf_path: str | os.PathLike[str]) -> bool:
    """Export HTML to A4 PDF through Playwright when available."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright is not installed. HTML has been generated. Install with: pip install playwright && python -m playwright install chromium")
        return False
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1240, "height": 1754})
            page.goto(Path(html_path).resolve().as_uri(), wait_until="networkidle")
            page.pdf(path=str(pdf_path), format="A4", print_background=True, margin={"top": "0", "right": "0", "bottom": "0", "left": "0"})
            browser.close()
        return Path(pdf_path).is_file() and Path(pdf_path).stat().st_size > 0
    except Exception as exc:
        warnings.warn(f"Playwright PDF export unavailable: {exc}")
        print("HTML has been generated. Please install Playwright Chromium with: python -m playwright install chromium")
        return False


def generate_report(args: argparse.Namespace) -> tuple[Path, Path, bool]:
    """Generate medical-style massage report HTML and optional PDF."""
    context = load_report_context(
        user_id=args.user_id,
        report_id=args.report_id,
        logo_path=args.logo_path,
        output_dir=args.output_dir,
        phone=args.phone,
        gender=args.gender,
        age=args.age,
        department=args.department,
        massage_part=args.massage_part,
        deepseek_api_key=args.deepseek_api_key,
    )
    html_path = render_html_report(context)
    pdf_path = Path(context["output_dir"]) / f"{args.user_id}_medical_style_massage_report.pdf"
    exported = export_pdf_with_playwright(html_path, pdf_path)
    return html_path, pdf_path, exported


def main() -> None:
    """Command-line entry point."""
    parser = argparse.ArgumentParser(description="Generate a medical-style smart massage detection report.")
    parser.add_argument("--user_id", required=True)
    parser.add_argument("--report_id", default=None)
    parser.add_argument("--logo_path", default=None)
    parser.add_argument("--deepseek_api_key", default=None)
    parser.add_argument("--output_dir", default="outputs")
    parser.add_argument("--phone", default="--")
    parser.add_argument("--gender", default="--")
    parser.add_argument("--age", default="--")
    parser.add_argument("--department", default="背部")
    parser.add_argument("--massage_part", default="背部")
    args = parser.parse_args()

    html_path, pdf_path, exported = generate_report(args)
    print(f"Medical style massage report HTML saved to: outputs/{html_path.name}")
    if exported:
        print(f"Medical style massage report PDF saved to: outputs/{pdf_path.name}")
    else:
        print("Medical style massage report PDF was not exported. Please install Playwright and Chromium, then rerun.")


if __name__ == "__main__":
    main()
