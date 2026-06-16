"""Generate a modern HTML/CSS smart massage report and export it to PDF.

This module is intentionally separate from the legacy ReportLab generator.
It reads the same alignment/stiffness outputs, renders a Jinja2 HTML report,
and uses Playwright/Chromium for high-fidelity A4 PDF export when available.
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
    from jinja2 import Environment, FileSystemLoader, select_autoescape
except ImportError:  # pragma: no cover - dependency guard.
    Environment = None
    FileSystemLoader = None
    select_autoescape = None

try:
    import config
except ImportError:  # pragma: no cover - supports direct execution nearby.
    class _FallbackConfig:
        output_dir = str(Path(__file__).resolve().parent / "outputs")

    config = _FallbackConfig()


BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = Path(getattr(config, "output_dir", BASE_DIR / "outputs"))
TEMPLATE_DIR = BASE_DIR / "templates"

SECTION_ORDER = ["Upper Back", "Mid Back", "Lower Back"]
SECTION_CN = {
    "Upper Back": "上背部",
    "Mid Back": "中背部",
    "Lower Back": "下背部",
}
SECTION_TODO = {
    "Upper Back": "Stretches",
    "Mid Back": "Posture Care",
    "Lower Back": "Release + Stretch",
}
SECTION_RECOMMENDATIONS = {
    "Upper Back": ["门框拉伸", "肩胛后缩训练", "泡沫轴胸椎放松"],
    "Mid Back": ["坐姿旋转拉伸", "胸椎伸展训练", "背阔肌放松"],
    "Lower Back": ["抱膝拉伸", "腘绳肌拉伸", "骨盆稳定训练"],
}
ACUPOINTS = {
    "Upper Back": [
        ("BL12", "Feng Men（风门）", "Trapezius / Rhomboid"),
        ("BL13", "Fei Shu（肺俞）", "Trapezius / Rhomboid"),
        ("BL14", "Jue Yin Shu（厥阴俞）", "Trapezius"),
        ("BL15", "Xin Shu（心俞）", "Trapezius"),
        ("BL16", "Du Shu（督俞）", "Trapezius"),
    ],
    "Mid Back": [
        ("BL17", "Ge Shu（膈俞）", "Latissimus dorsi"),
        ("EXB3", "Wei Wan Xia Shu（胃脘下俞）", "Latissimus dorsi"),
        ("BL18", "Gan Shu（肝俞）", "Latissimus dorsi"),
        ("BL19", "Dan Shu（胆俞）", "Latissimus dorsi"),
        ("BL20", "Pi Shu（脾俞）", "Latissimus dorsi"),
        ("BL21", "Wei Shu（胃俞）", "Latissimus dorsi"),
    ],
    "Lower Back": [
        ("BL22", "San Jiao Shu（三焦俞）", "Thoracolumbar fascia"),
        ("BL23", "Shen Shu（肾俞）", "Thoracolumbar fascia"),
        ("BL24", "Qi Hai Shu（气海俞）", "Thoracolumbar fascia"),
        ("BL25", "Da Chang Shu（大肠俞）", "Thoracolumbar fascia"),
        ("BL26", "Guan Yuan Shu（关元俞）", "Thoracolumbar fascia"),
    ],
}


def file_url(path: str | os.PathLike[str] | None) -> str | None:
    if not path:
        return None
    return Path(path).resolve().as_uri()


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_report_data(user_id: str) -> dict[str, Any]:
    """Load alignment first, stiffness second, and fall back to demo data."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    alignment = load_json(OUTPUT_DIR / f"{user_id}_spatial_temporal_alignment.json")
    stiffness = load_json(OUTPUT_DIR / f"{user_id}_stiffness_stats.json")
    if alignment and stiffness:
        mode = "alignment+stiffness"
    elif alignment:
        mode = "alignment"
    elif stiffness:
        mode = "stiffness"
    else:
        mode = "demo"
    return {
        "user_id": user_id,
        "alignment": alignment,
        "stiffness": stiffness,
        "mode": mode,
    }


def demo_alignment() -> dict[str, Any]:
    return {
        "overall": {
            "total_samples": 160,
            "contact_samples": 128,
            "contact_ratio": 0.8,
            "total_duration_s": 8.0,
            "contact_duration_s": 6.4,
            "mean_contact_force_N": 7.8,
            "max_contact_force_N": 13.2,
        },
        "by_section": [
            {"section": "Upper Back", "duration_s": 1.8, "mean_force_N": 6.4, "max_force_N": 10.2, "main_acupoints": ["风门", "肺俞"], "grade": "B", "label": "Moderate", "to_do": "Stretches"},
            {"section": "Mid Back", "duration_s": 2.2, "mean_force_N": 7.5, "max_force_N": 12.1, "main_acupoints": ["膈俞", "肝俞"], "grade": "B", "label": "Moderate", "to_do": "Posture Care"},
            {"section": "Lower Back", "duration_s": 2.4, "mean_force_N": 10.8, "max_force_N": 13.2, "main_acupoints": ["肾俞", "大肠俞"], "grade": "C", "label": "Higher", "to_do": "Release + Stretch"},
        ],
        "by_acupoint": [
            {"name": "肾俞", "section": "Lower Back", "duration_s": 0.8, "mean_force_N": 10.1, "max_force_N": 13.2, "attention_level": "attention"},
            {"name": "大肠俞", "section": "Lower Back", "duration_s": 0.6, "mean_force_N": 9.3, "max_force_N": 12.6, "attention_level": "normal"},
            {"name": "膈俞", "section": "Mid Back", "duration_s": 0.5, "mean_force_N": 7.9, "max_force_N": 10.8, "attention_level": "normal"},
            {"name": "风门", "section": "Upper Back", "duration_s": 0.4, "mean_force_N": 6.5, "max_force_N": 9.6, "attention_level": "normal"},
            {"name": "肺俞", "section": "Upper Back", "duration_s": 0.4, "mean_force_N": 6.1, "max_force_N": 8.9, "attention_level": "normal"},
        ],
        "by_region": [],
        "aligned_records": [],
    }


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def fmt_num(value: Any, digits: int = 1) -> str:
    if value is None:
        return "--"
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "--"


def grade_from_force(mean_force: Any) -> str:
    value = as_float(mean_force)
    if value < 5:
        return "A"
    if value < 10:
        return "B"
    if value < 15:
        return "C"
    return "D"


def grade_label(grade: str) -> str:
    return {"A": "Mild", "B": "Moderate", "C": "Higher", "D": "Severe"}.get(grade, "Mild")


def grade_label_cn(grade: str) -> str:
    return {"A": "轻度紧张", "B": "中度紧张", "C": "偏高紧张", "D": "高关注"}.get(grade, "中度紧张")


def attention_text(level: str | None) -> str:
    return {"normal": "正常", "attention": "需关注", "high": "高关注"}.get(str(level or "normal"), "正常")


def normalize_sections(source: dict[str, Any]) -> list[dict[str, Any]]:
    raw_sections = {item.get("section"): item for item in source.get("by_section", [])}
    stiffness_sections = {item.get("section"): item for item in source.get("sections", [])}
    sections = []
    for section in SECTION_ORDER:
        item = dict(raw_sections.get(section) or stiffness_sections.get(section) or {})
        mean_force = item.get("mean_force_N")
        grade = item.get("grade") or grade_from_force(mean_force)
        sections.append({
            "section": section,
            "section_cn": SECTION_CN[section],
            "grade": grade,
            "label": item.get("label") or grade_label(grade),
            "label_cn": grade_label_cn(grade),
            "to_do": item.get("to_do") or SECTION_TODO[section],
            "contact_count": int(as_float(item.get("contact_count") or item.get("sample_count"))),
            "duration_s": as_float(item.get("duration_s")),
            "mean_force_N": mean_force,
            "max_force_N": item.get("max_force_N"),
            "main_acupoints": item.get("main_acupoints") or [],
            "force_marker": max(2, min(98, as_float(mean_force) / 20 * 100)),
            "acupoints": [
                {"label": label, "name": name, "muscle": muscle}
                for label, name, muscle in ACUPOINTS[section]
            ],
            "recommendations": SECTION_RECOMMENDATIONS[section],
        })
    return sections


def section_summary(section: dict[str, Any]) -> str:
    points = "、".join(section["main_acupoints"][:5]) or "主要接触点"
    mean_force = fmt_num(section.get("mean_force_N"), 2)
    max_force = fmt_num(section.get("max_force_N"), 2)
    if section["section"] == "Upper Back":
        return f"本次上背部按摩覆盖了 {points} 等区域，平均按压力为 {mean_force} N，整体处于 {section['label']} 水平。建议关注肩胛带周围放松与胸椎伸展。"
    if section["section"] == "Mid Back":
        return f"本次中背部按摩主要作用于 {points} 等区域，平均按压力为 {mean_force} N。若该区域接触时长较长或最大力度偏高，建议后续降低初始力度并采用渐进加力策略。"
    return f"本次下背部按摩接触时长为 {fmt_num(section.get('duration_s'), 2)} s，最大按压力为 {max_force} N。建议后续重点进行腰背放松与柔韧性维护，同时避免靠近脊柱中线强按。"


def build_report_context(user_id: str, logo_path: str | None = None, report_id: str | None = None) -> dict[str, Any]:
    data = load_report_data(user_id)
    source = data["alignment"] or data["stiffness"] or demo_alignment()
    overall = source.get("overall", {})
    sections = normalize_sections(source)
    for section in sections:
        section["summary"] = section_summary(section)

    grade_order = {"A": 1, "B": 2, "C": 3, "D": 4}
    focus_section = max(sections, key=lambda item: (grade_order.get(item["grade"], 1), item["duration_s"], as_float(item.get("max_force_N"))))
    overall_grade = focus_section["grade"]
    by_acupoint = sorted(
        source.get("by_acupoint", []),
        key=lambda item: (as_float(item.get("contact_count")), as_float(item.get("duration_s"))),
        reverse=True,
    )
    top_points = [
        {
            "name": item.get("name", "--"),
            "section": item.get("section", "--"),
            "duration_s": fmt_num(item.get("duration_s"), 2),
            "mean_force_N": fmt_num(item.get("mean_force_N"), 2),
            "max_force_N": fmt_num(item.get("max_force_N"), 2),
            "attention_level": item.get("attention_level") or "normal",
            "status": attention_text(item.get("attention_level")),
        }
        for item in by_acupoint[:5]
    ]
    max_force = as_float(overall.get("max_contact_force_N") or overall.get("max_force_N"))
    high_force_count = sum(1 for item in source.get("aligned_records", []) if as_float(item.get("force_N") or item.get("force")) >= 15)
    high_risk = any(
        "spine_center" in str(item.get("section", "")).lower()
        or "spine_center" in str(item.get("region", "")).lower()
        or "high risk" in str(item.get("region", "")).lower()
        for item in source.get("by_acupoint", []) + source.get("by_region", [])
    )
    plot_xy = OUTPUT_DIR / f"{user_id}_trajectory_acupoints_xy.png"
    plot_3d = OUTPUT_DIR / f"{user_id}_trajectory_acupoints_3d.png"
    summary_sentence = (
        f"本次按摩主要覆盖{focus_section['section_cn']}区域，整体力度处于{focus_section['label_cn']}范围，"
        f"{focus_section['section_cn']}建议重点关注。"
    )
    report_id = report_id or f"DEMO-{datetime.now().year}-001"
    return {
        "user_id": user_id,
        "report_id": report_id,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "mode": data["mode"],
        "css_url": file_url(TEMPLATE_DIR / "smart_massage_report.css"),
        "logo_url": file_url(logo_path) if logo_path and Path(logo_path).is_file() else None,
        "overall_grade": overall_grade,
        "overall_label": grade_label_cn(overall_grade),
        "summary_sentence": summary_sentence,
        "overall": {
            "mean_force": fmt_num(overall.get("mean_contact_force_N") or overall.get("mean_force_N"), 2),
            "max_force": fmt_num(overall.get("max_contact_force_N") or overall.get("max_force_N"), 2),
            "contact_duration": fmt_num(overall.get("contact_duration_s"), 2),
            "contact_ratio": f"{as_float(overall.get('contact_ratio')) * 100:.0f}%",
        },
        "focus_section": focus_section,
        "sections": sections,
        "top_points": top_points,
        "trajectory_xy_url": file_url(plot_xy) if plot_xy.is_file() else None,
        "trajectory_3d_url": file_url(plot_3d) if plot_3d.is_file() else None,
        "safety": {
            "max_force": fmt_num(max_force, 2),
            "high_force": "是" if high_force_count else "否",
            "spine_risk": "需避让" if high_risk else "未见明显风险",
            "overall": "建议渐进加力" if max_force >= 15 else "力度较保守",
            "force_text": "本次存在局部较高力度接触，建议下次降低相关区域初始力度并采用渐进加力。" if max_force >= 15 else "本次未检测到持续高力度按压，整体力度处于较保守范围。",
            "risk_text": "检测到靠近脊柱中线或高风险区域的接触，建议后续路径规划中增加避让距离。" if high_risk else "本次未检测到明显靠近脊柱中线的高风险接触。",
            "focus": "、".join([s["section_cn"] for s in sections if s["grade"] in ("C", "D")]) or focus_section["section_cn"],
            "start_force": "低力度起步，并根据舒适度逐步增加",
            "avoid": "脊柱中线及未知区域",
            "care": "拉伸、放松、稳定训练",
        },
    }


def _brand_html(context: dict[str, Any]) -> str:
    if context.get("logo_url"):
        return f'<div class="brand"><img src="{context["logo_url"]}" alt="LSCURE logo" /></div>'
    return '<div class="brand"><span>LSCURE</span></div>'


def _badge(grade: str, text: str | None = None) -> str:
    return f'<span class="badge grade-{grade}">{text or grade}</span>'


def _render_fallback_html(context: dict[str, Any]) -> str:
    """Render the same report shape without Jinja2 for offline usability."""
    brand = _brand_html(context)
    sections = context["sections"]
    top_points = context["top_points"]
    section_rows = "".join(
        "<div class=\"table-row\">"
        f"<div><strong>{s['section']}</strong><small>{s['section_cn']}</small></div>"
        f"{_badge(s['grade'])}<span>{s['label']}</span><span>{s['to_do']}</span>"
        "</div>"
        for s in sections
    )
    analysis_cards = """
      <article class="info-card"><i>01</i><h3>区域识别与时空对齐</h3><p>系统基于统一相机坐标系下的机械臂 TCP 轨迹、穴位 3D 点云坐标与实时按压力数据，判断每个采样时刻对应的按摩位置。</p></article>
      <article class="info-card"><i>02</i><h3>按摩覆盖与力度分析</h3><p>报告统计各穴位和背部区域的接触次数、接触时长、平均力度与最大力度，用于评估本次按摩覆盖范围和力度稳定性。</p></article>
      <article class="info-card"><i>03</i><h3>安全力度与后续建议</h3><p>系统根据区域风险、接触距离和按压力水平生成安全提示，辅助规划下一次按摩重点区域、推荐力度和避让区域。</p></article>
    """
    top_rows = "".join(
        "<tr>"
        f"<td>{p['name']}</td><td>{p['section']}</td><td>{p['duration_s']} s</td>"
        f"<td>{p['mean_force_N']} N</td><td>{p['max_force_N']} N</td>"
        f"<td><span class=\"status status-{p['attention_level']}\">{p['status']}</span></td>"
        "</tr>"
        for p in top_points
    )
    trajectory_xy = (
        f'<img src="{context["trajectory_xy_url"]}" alt="Trajectory XY alignment" />'
        if context.get("trajectory_xy_url")
        else '<div class="empty-state">未检测到轨迹可视化图，请先运行空间时间对齐模块。</div>'
    )
    trajectory_3d = (
        f'<div class="image-card"><img src="{context["trajectory_3d_url"]}" alt="Trajectory 3D alignment" /></div>'
        if context.get("trajectory_3d_url")
        else ""
    )

    section_pages = []
    for section in sections:
        acu_rows = "".join(
            f"<tr><td>{p['label']}</td><td>{p['name']}</td><td>{p['muscle']}</td></tr>"
            for p in section["acupoints"]
        )
        recs = "".join(f"<li>{item}</li>" for item in section["recommendations"])
        main_points = "、".join(section["main_acupoints"][:3]) or "暂无统计"
        section_pages.append(f"""
  <section class="page">
    <header class="report-header compact">
      {brand}
      <div><h2>{section['section']} / {section['section_cn']}分析</h2><p>Section Assessment</p></div>
      {_badge(section['grade'], f"{section['grade']} {section['label']}")}
    </header>
    <div class="metric-grid four section-metrics">
      <article class="metric-card slim"><span>接触时长</span><strong>{section['duration_s']:.2f} s</strong></article>
      <article class="metric-card slim"><span>平均力度</span><strong>{section.get('mean_force_N') if section.get('mean_force_N') is not None else '--'} N</strong></article>
      <article class="metric-card slim"><span>最大力度</span><strong>{section.get('max_force_N') if section.get('max_force_N') is not None else '--'} N</strong></article>
      <article class="metric-card slim"><span>主要穴位</span><strong>{main_points}</strong></article>
    </div>
    <section class="content-grid two">
      <div class="card"><div class="card-head"><h3>穴位表</h3><span>Acupoints</span></div><table class="soft-table compact-table"><thead><tr><th>Label</th><th>Acupoint Name</th><th>Muscle / Region</th></tr></thead><tbody>{acu_rows}</tbody></table></div>
      <div class="card force-card"><div class="card-head"><h3>力度水平</h3><span>Force Level</span></div><div class="force-scale"><span>Low</span><span>Medium</span><span>High</span><i style="left: {section['force_marker']}%"></i></div><p>当前平均按压力位于上方标记位置，建议从舒适力度开始并逐步调整。</p></div>
    </section>
    <section class="content-grid two lower-cards">
      <article class="card text-card"><h3>Summary</h3><p>{section['summary']}</p></article>
      <article class="card text-card"><h3>Recommendation</h3><ul>{recs}</ul></article>
    </section>
    <footer class="page-footer">本报告为项目演示生成，仅用于研究与功能展示，不构成医疗建议。</footer>
  </section>
""")

    visual_marks = "".join(
        f"""
          <g class="section-mark grade-{section['grade']}">
            {('<rect x="92" y="94" width="136" height="74" rx="28" /><text x="160" y="137">Upper</text>' if section['section'] == 'Upper Back' else '')}
            {('<rect x="82" y="178" width="156" height="82" rx="30" /><text x="160" y="225">Mid</text>' if section['section'] == 'Mid Back' else '')}
            {('<rect x="92" y="270" width="136" height="76" rx="28" /><text x="160" y="315">Lower</text>' if section['section'] == 'Lower Back' else '')}
          </g>
        """
        for section in sections
    )
    top1 = top_points[0]["name"] if top_points else "暂无"
    safety = context["safety"]
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>背部智能按摩评估报告 - {context['user_id']}</title>
  <link rel="stylesheet" href="{context['css_url']}" />
</head>
<body>
  <section class="page cover-page">
    <header class="report-header cover-header">
      {brand}
      <div class="title-block"><h1>背部智能按摩评估报告</h1><p>Smart Back Massage Assessment Report</p></div>
      <div class="meta"><span>报告编号</span><strong>{context['report_id']}</strong><span>用户编号</span><strong>{context['user_id']}</strong><span>生成时间</span><strong>{context['generated_at']}</strong></div>
    </header>
    <main class="hero">
      <div class="hero-left"><p class="eyebrow">Overall Back Status</p><div class="grade-hero grade-{context['overall_grade']}">{context['overall_grade']}</div><h2>{context['overall_label']}</h2><p class="summary-line">{context['summary_sentence']}</p></div>
      <div class="back-visual-card"><svg class="back-visual" viewBox="0 0 320 420" role="img" aria-label="Back section overview"><path class="body-line" d="M160 44 C103 63 76 128 78 210 C80 301 115 366 160 388 C205 366 240 301 242 210 C244 128 217 63 160 44Z" /><path class="spine-line" d="M160 76 C152 118 171 142 160 185 C149 228 169 256 160 304 C154 335 160 360 160 378" />{visual_marks}</svg><p>颜色表示本次按摩数据中各区域的关注等级。</p></div>
    </main>
    <div class="metric-grid four">
      <article class="metric-card"><i>F</i><span>平均按压力</span><strong>{context['overall']['mean_force']}<small>N</small></strong><p>有效接触平均值</p></article>
      <article class="metric-card"><i>M</i><span>最大按压力</span><strong>{context['overall']['max_force']}<small>N</small></strong><p>本次局部峰值</p></article>
      <article class="metric-card"><i>T</i><span>有效接触时长</span><strong>{context['overall']['contact_duration']}<small>s</small></strong><p>轨迹与穴位匹配后统计</p></article>
      <article class="metric-card"><i>A</i><span>重点关注区域</span><strong>{context['focus_section']['section']}</strong><p>{context['focus_section']['section_cn']}</p></article>
    </div>
    <section class="content-grid two"><div class="card"><div class="card-head"><h3>Section Summary</h3><span>{context['mode']}</span></div><div class="modern-table section-summary">{section_rows}</div></div><div class="card legend-card"><h3>Grade Legend</h3><div class="legend-row">{_badge('A')}<p>Mild / 轻度紧张</p></div><div class="legend-row">{_badge('B')}<p>Moderate / 中度紧张</p></div><div class="legend-row">{_badge('C')}<p>Higher / 偏高紧张</p></div><div class="legend-row">{_badge('D')}<p>Severe / 高关注</p></div></div></section>
    <section class="analysis-grid">{analysis_cards}</section>
    <footer class="page-footer">本报告为项目演示生成，仅用于研究与功能展示，不构成医疗建议。</footer>
  </section>
  <section class="page">
    <header class="report-header compact">{brand}<div><h2>机械臂按摩轨迹与穴位对齐</h2><p>该图展示机械臂 TCP 轨迹与穴位 3D 点云坐标的空间匹配关系，用于判断每个时刻按摩探头作用的位置。</p></div></header>
    <div class="trajectory-layout"><div class="image-card large">{trajectory_xy}</div>{trajectory_3d}</div>
    <div class="metric-grid five"><article class="metric-card slim"><span>总采样点数</span><strong>{context['overall']['contact_ratio']}</strong><p>有效接触比例</p></article><article class="metric-card slim"><span>平均按压力</span><strong>{context['overall']['mean_force']} N</strong></article><article class="metric-card slim"><span>最大按压力</span><strong>{context['overall']['max_force']} N</strong></article><article class="metric-card slim"><span>有效接触时长</span><strong>{context['overall']['contact_duration']} s</strong></article><article class="metric-card slim"><span>TOP 1 穴位</span><strong>{top1}</strong></article></div>
    <div class="card"><div class="card-head"><h3>TOP 5 主要按摩穴位</h3><span>Acupoint Coverage</span></div><table class="soft-table"><thead><tr><th>穴位</th><th>分区</th><th>接触时长</th><th>平均力度</th><th>最大力度</th><th>状态</th></tr></thead><tbody>{top_rows}</tbody></table></div>
    <footer class="page-footer">本报告为项目演示生成，仅用于研究与功能展示，不构成医疗建议。</footer>
  </section>
  {''.join(section_pages)}
  <section class="page">
    <header class="report-header compact">{brand}<div><h2>安全力度与下次按摩建议</h2><p>Safety & Next Session Plan</p></div></header>
    <section class="metric-grid four"><article class="metric-card"><span>最大按压力</span><strong>{safety['max_force']} N</strong></article><article class="metric-card"><span>高力度接触</span><strong>{safety['high_force']}</strong></article><article class="metric-card"><span>脊柱中线风险</span><strong>{safety['spine_risk']}</strong></article><article class="metric-card"><span>整体安全评价</span><strong>{safety['overall']}</strong></article></section>
    <section class="content-grid two"><article class="notice-card ok"><h3>高力度提示</h3><p>{safety['force_text']}</p></article><article class="notice-card"><h3>避让区提示</h3><p>{safety['risk_text']}</p></article></section>
    <section class="card next-plan"><div class="card-head"><h3>下次按摩建议</h3><span>Next Session</span></div><div class="plan-grid"><div><span>建议重点区域</span><strong>{safety['focus']}</strong></div><div><span>建议起始力度</span><strong>{safety['start_force']}</strong></div><div><span>建议避让区域</span><strong>{safety['avoid']}</strong></div><div><span>建议拉伸动作</span><strong>{safety['care']}</strong></div></div></section>
    <footer class="page-footer">本报告为项目演示生成，仅用于研究与功能展示，不构成医疗建议。</footer>
  </section>
</body>
</html>
"""


def render_html_report(context: dict[str, Any]) -> Path:
    if Environment is None:
        print("Jinja2 is not installed. Using built-in fallback renderer. Install with: pip install jinja2")
        html = _render_fallback_html(context)
    else:
        env = Environment(
            loader=FileSystemLoader(str(TEMPLATE_DIR)),
            autoescape=select_autoescape(["html", "xml", "jinja"]),
        )
        template = env.get_template("smart_massage_report.jinja")
        html = template.render(**context)
    output_path = OUTPUT_DIR / f"{context['user_id']}_smart_massage_report.html"
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return output_path


def export_pdf_with_playwright(html_path: str | os.PathLike[str], pdf_path: str | os.PathLike[str]) -> bool:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright is not installed. HTML has been generated. Install with: pip install playwright && python -m playwright install chromium")
        return False

    html_url = Path(html_path).resolve().as_uri()
    pdf_path = Path(pdf_path)
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1240, "height": 1754})
            page.goto(html_url, wait_until="networkidle")
            page.pdf(
                path=str(pdf_path),
                format="A4",
                print_background=True,
                margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
            )
            browser.close()
        return pdf_path.is_file() and pdf_path.stat().st_size > 0
    except Exception as exc:  # pragma: no cover - depends on local browser install.
        warnings.warn(f"Playwright PDF export unavailable: {exc}")
        print("HTML has been generated. Please install Playwright Chromium with: python -m playwright install chromium")
        return False


def generate_html_report(user_id: str, logo_path: str | None = None, report_id: str | None = None) -> tuple[Path, Path, bool]:
    context = build_report_context(user_id, logo_path=logo_path, report_id=report_id)
    html_path = render_html_report(context)
    pdf_path = OUTPUT_DIR / f"{user_id}_smart_massage_report.pdf"
    exported = export_pdf_with_playwright(html_path, pdf_path)
    return html_path, pdf_path, exported


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a modern HTML/CSS smart massage report.")
    parser.add_argument("--user_id", required=True)
    parser.add_argument("--logo_path", default=None)
    parser.add_argument("--report_id", default=None)
    args = parser.parse_args()

    html_path, pdf_path, exported = generate_html_report(args.user_id, logo_path=args.logo_path, report_id=args.report_id)
    print(f"Smart massage HTML saved to: outputs/{html_path.name}")
    if exported:
        print(f"Smart massage report saved to: outputs/{pdf_path.name}")
    else:
        print("Smart massage PDF was not exported. Please install Playwright and Chromium, then rerun.")


if __name__ == "__main__":
    main()
