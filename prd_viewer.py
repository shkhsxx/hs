import re
import streamlit as st
import streamlit.components.v1 as components
from pathlib import Path

st.set_page_config(
    page_title="SecondBoost PRD 문서",
    page_icon="📄",
    layout="wide",
)

OUTPUT_DIR = Path(__file__).parent / "output"

def _read(name):
    return (OUTPUT_DIR / name).read_text(encoding="utf-8")

def _decisions_cases():
    text = _read("decisions.md")
    idx = text.find("\n# 전체 요약")
    return text[:idx].rstrip() if idx != -1 else text

def _decisions_summary():
    text = _read("decisions.md")
    idx = text.find("\n# 전체 요약")
    return text[idx+1:].lstrip() if idx != -1 else ""

DOCS = {
    "📋 PRD 문서":           ("prd_output.md",      _read,  "prd_output.md"),
    "🔴 의사결정 요청서":    ("decision_request.md", _read,  "decision_request.md"),
    "🗂️ 요구사항 구조화":   ("decisions.md",        None,   _decisions_cases),
    "📊 전체 요약":          ("decisions.md",        None,   _decisions_summary),
}

# ── 의사결정 항목 파싱 ────────────────────────────────────────────────
DECISION_TIERS = {
    "B": {"label": "🔴 Blocker", "color": "#E85454", "bg": "rgba(232,84,84,0.10)", "border": "rgba(232,84,84,0.28)"},
    "W": {"label": "🟡 주의",    "color": "#F0A429", "bg": "rgba(240,164,41,0.10)", "border": "rgba(240,164,41,0.28)"},
    "R": {"label": "🟢 참고",    "color": "#2EC88E", "bg": "rgba(46,200,142,0.10)", "border": "rgba(46,200,142,0.28)"},
}

def has_decisions(text):
    return bool(re.search(r"^### [BWR]-\d+\.", text, re.MULTILINE))

def parse_decisions(text):
    """
    Returns list of groups:
      [ (tier, tier_intro, [ (code, title, case_ref, impact, urgency, content), ... ]), ... ]
    tier_intro: the ## 🔴 Blocker ... section header + any intro text before first ###
    """
    # Split into tier sections by ## 🔴 / ## 🟡 / ## 🟢
    tier_pattern = r"(?=^## (?:🔴|🟡|🟢))"
    tier_chunks = re.split(tier_pattern, text, flags=re.MULTILINE)

    # Non-tier preamble
    preamble = ""
    groups = []

    for chunk in tier_chunks:
        # Is this a tier section?
        tier_m = re.match(r"^## (🔴|🟡|🟢)\s*(Blocker|주의|참고)[^\n]*\n", chunk)
        if not tier_m:
            preamble += chunk
            continue

        emoji = tier_m.group(1)
        tier_key = {"🔴": "B", "🟡": "W", "🟢": "R"}[emoji]

        # Split into individual items by ### B-xx / W-xx / R-xx
        item_pattern = r"(?=^### [BWR]-\d+\.)"
        parts = re.split(item_pattern, chunk, flags=re.MULTILINE)

        tier_intro = parts[0]  # tier heading + preamble text
        items = []

        for part in parts[1:]:
            if not part.strip():
                continue
            # ### B-01. 제목
            head_m = re.match(r"^### ([BWR]-\d+)\.\s*(.+)", part)
            if not head_m:
                continue
            code  = head_m.group(1)
            title = head_m.group(2).strip()

            # 관련 케이스
            case_m = re.search(r"\*\*관련 케이스:\*\*\s*(.+)", part)
            case_ref = case_m.group(1).strip() if case_m else ""

            # 임팩트
            imp_m = re.search(r"\*\*임팩트:\*\*\s*(.+)", part)
            impact = imp_m.group(1).strip() if imp_m else ""

            # 긴급도
            urg_m = re.search(r"\*\*긴급도:\*\*\s*(.+)", part)
            urgency = urg_m.group(1).strip() if urg_m else ""

            items.append((code, title, case_ref, impact, urgency, part))

        groups.append((tier_key, tier_intro, items))

    return preamble, groups

# ── 케이스 파싱 ──────────────────────────────────────────────────────
CASE_PATTERNS = [
    r"^## Case (\d+)",              # decisions.md
    r"^## \[케이스 (\d+)\]",        # prd_output.md
]

def has_cases(text):
    for p in CASE_PATTERNS:
        if re.search(p, text, re.MULTILINE):
            return True
    return False

def parse_cases(text):
    """(preamble, [(num, feature, type_, priority, conflict, content), ...])"""
    pattern = r"(?=^## (?:Case \d+|\[케이스 \d+\]))"
    first = re.search(r"^## (?:Case \d+|\[케이스 \d+\])", text, re.MULTILINE)
    if not first:
        return text, []

    preamble = text[:first.start()]
    chunks = re.split(pattern, text[first.start():], flags=re.MULTILINE)

    cases = []
    for chunk in chunks:
        if not chunk.strip():
            continue

        # 케이스 번호
        num_m = re.search(r"(?:Case |케이스 )(\d+)", chunk)
        num = num_m.group(1).zfill(2) if num_m else "??"

        # 기능명 (decisions: **기능명:**, prd: 기능명: 뒤)
        feat_m = re.search(r"\*\*기능명:\*\*\s*(.+)|기능명:\s*(.+)", chunk)
        feature = (feat_m.group(1) or feat_m.group(2)).strip() if feat_m else ""

        # 유형 (decisions만)
        type_m = re.search(r"\*\*유형:\*\*\s*(.+)", chunk)
        type_ = type_m.group(1).strip() if type_m else ""

        # 우선순위
        prio_m = re.search(r"\*\*(P[123])\*\*", chunk)
        priority = prio_m.group(1) if prio_m else "P2"

        # Conflict 여부
        conflict = bool(re.search(r"\[CONFLICT\]|CONFLICT", chunk, re.IGNORECASE))

        cases.append((num, feature, type_, priority, conflict, chunk))

    return preamble, cases

# ── 앵커 ID 생성 ──────────────────────────────────────────────────────
def heading_to_id(text):
    text = re.sub(r"[*_`#\[\]()\U0001F000-\U0001FFFF]", "", text)
    text = re.sub(r"\s+", "-", text.strip().lower())
    text = re.sub(r"-+", "-", text).strip("-")
    return text or "section"

# ── TOC 추출 (h2, h3) ────────────────────────────────────────────────
def extract_toc(text, max_level=2):
    toc = []
    for line in text.split("\n"):
        m = re.match(r"^(#{1,3})\s+(.+)", line)
        if m:
            level = len(m.group(1))
            if level > max_level:
                continue
            heading = m.group(2).strip()
            slug = heading_to_id(heading)
            # 표시용 이름: 이모지·특수문자 제거
            display = re.sub(r"[🔴🟡🟢📋🗂️📊]", "", heading).strip()
            toc.append((level, display, slug))
    return toc

# ── 마크다운 전처리 ───────────────────────────────────────────────────
MATRIX_HTML = """
<div style="margin:20px 0 24px;">
  <div style="display:inline-block;border:1px solid rgba(255,255,255,0.1);border-radius:10px;overflow:hidden;font-size:13px;">
    <div style="display:flex;align-items:center;">
      <div style="width:72px;"></div>
      <div style="flex:1;text-align:center;padding:8px 0;font-size:11px;font-weight:700;
                  letter-spacing:.08em;color:#5A6280;border-bottom:1px solid rgba(255,255,255,0.07);
                  text-transform:uppercase;">임팩트 높음</div>
    </div>
    <div style="display:flex;border-bottom:1px solid rgba(255,255,255,0.07);">
      <div style="width:72px;display:flex;align-items:center;justify-content:center;
                  border-right:1px solid rgba(255,255,255,0.07);padding:0 10px;">
        <div style="writing-mode:vertical-rl;transform:rotate(180deg);font-size:10px;
                    font-weight:700;letter-spacing:.1em;color:#5A6280;text-transform:uppercase;">긴급도 낮음</div>
      </div>
      <div style="flex:1;padding:20px 32px;background:rgba(240,164,41,0.08);
                  border-right:1px solid rgba(255,255,255,0.07);text-align:center;">
        <div style="font-size:22px;margin-bottom:6px;">🟡</div>
        <div style="font-size:14px;font-weight:700;color:#F0A429;">주의</div>
        <div style="font-size:11px;color:#7A6030;margin-top:4px;">임팩트↑ 긴급도↓</div>
      </div>
      <div style="flex:1;padding:20px 32px;background:rgba(232,84,84,0.1);text-align:center;">
        <div style="font-size:22px;margin-bottom:6px;">🔴</div>
        <div style="font-size:14px;font-weight:700;color:#E85454;">Blocker</div>
        <div style="font-size:11px;color:#7A3030;margin-top:4px;">임팩트↑ 긴급도↑</div>
      </div>
    </div>
    <div style="display:flex;">
      <div style="width:72px;display:flex;align-items:center;justify-content:center;
                  border-right:1px solid rgba(255,255,255,0.07);padding:0 10px;">
        <div style="writing-mode:vertical-rl;transform:rotate(180deg);font-size:10px;
                    font-weight:700;letter-spacing:.1em;color:#5A6280;text-transform:uppercase;">긴급도 높음</div>
      </div>
      <div style="flex:1;padding:20px 32px;background:rgba(46,200,142,0.07);
                  border-right:1px solid rgba(255,255,255,0.07);text-align:center;">
        <div style="font-size:22px;margin-bottom:6px;">🟢</div>
        <div style="font-size:14px;font-weight:700;color:#2EC88E;">참고</div>
        <div style="font-size:11px;color:#207050;margin-top:4px;">임팩트↓ 긴급도↓</div>
      </div>
      <div style="flex:1;padding:20px 32px;background:rgba(240,164,41,0.05);text-align:center;">
        <div style="font-size:22px;margin-bottom:6px;">🟡</div>
        <div style="font-size:14px;font-weight:700;color:#C89030;">주의</div>
        <div style="font-size:11px;color:#7A6030;margin-top:4px;">임팩트↓ 긴급도↑</div>
      </div>
    </div>
    <div style="display:flex;align-items:center;">
      <div style="width:72px;"></div>
      <div style="flex:1;text-align:center;padding:8px 0;font-size:11px;font-weight:700;
                  letter-spacing:.08em;color:#5A6280;border-top:1px solid rgba(255,255,255,0.07);
                  text-transform:uppercase;">임팩트 낮음</div>
    </div>
  </div>
</div>
"""

SCHEDULE_HTML = """
<div style="margin:20px 0 28px;">
  <div style="display:flex;gap:0;margin-bottom:4px;">
    <div style="display:flex;flex-direction:column;align-items:center;margin-right:16px;">
      <div style="width:36px;height:36px;border-radius:50%;background:#E85454;
                  display:flex;align-items:center;justify-content:center;
                  font-size:11px;font-weight:800;color:white;flex-shrink:0;">W1</div>
      <div style="width:2px;flex:1;background:rgba(232,84,84,0.25);min-height:56px;margin-top:4px;"></div>
    </div>
    <div style="padding-top:6px;padding-bottom:20px;">
      <div style="font-size:15px;font-weight:800;color:#E85454;margin-bottom:8px;letter-spacing:-.01em;">
        Week 1 <span style="font-size:11px;font-weight:600;background:rgba(232,84,84,0.15);
        color:#E85454;border:1px solid rgba(232,84,84,0.3);padding:2px 8px;border-radius:20px;margin-left:6px;">즉시</span>
      </div>
      <div style="display:flex;flex-direction:column;gap:6px;">
        <div style="display:flex;align-items:center;gap:8px;">
          <span style="font-size:11px;font-weight:700;background:rgba(232,84,84,0.12);color:#E85454;
                       border:1px solid rgba(232,84,84,0.25);padding:2px 8px;border-radius:4px;flex-shrink:0;">B-01</span>
          <span style="font-size:13px;color:#C8D0F0;">인증 방식 결정</span>
          <span style="font-size:11px;color:#4E5670;margin-left:auto;">PO + 보안팀</span>
        </div>
        <div style="display:flex;align-items:center;gap:8px;">
          <span style="font-size:11px;font-weight:700;background:rgba(232,84,84,0.12);color:#E85454;
                       border:1px solid rgba(232,84,84,0.25);padding:2px 8px;border-radius:4px;flex-shrink:0;">B-02</span>
          <span style="font-size:13px;color:#C8D0F0;">자동 저장 위치 결정</span>
          <span style="font-size:11px;color:#4E5670;margin-left:auto;">PO</span>
        </div>
      </div>
    </div>
  </div>
  <div style="display:flex;gap:0;margin-bottom:4px;">
    <div style="display:flex;flex-direction:column;align-items:center;margin-right:16px;">
      <div style="width:36px;height:36px;border-radius:50%;background:#C07030;
                  display:flex;align-items:center;justify-content:center;
                  font-size:10px;font-weight:800;color:white;flex-shrink:0;">W1~2</div>
      <div style="width:2px;flex:1;background:rgba(240,164,41,0.2);min-height:48px;margin-top:4px;"></div>
    </div>
    <div style="padding-top:6px;padding-bottom:20px;">
      <div style="font-size:15px;font-weight:800;color:#F0A429;margin-bottom:8px;">Week 1~2</div>
      <div style="display:flex;align-items:center;gap:8px;">
        <span style="font-size:11px;font-weight:700;background:rgba(232,84,84,0.12);color:#E85454;
                     border:1px solid rgba(232,84,84,0.25);padding:2px 8px;border-radius:4px;flex-shrink:0;">B-03</span>
        <span style="font-size:13px;color:#C8D0F0;">탈퇴 후 데이터 보관 기간</span>
        <span style="font-size:11px;color:#4E5670;margin-left:auto;">PO + 법무</span>
      </div>
    </div>
  </div>
  <div style="display:flex;gap:0;margin-bottom:4px;">
    <div style="display:flex;flex-direction:column;align-items:center;margin-right:16px;">
      <div style="width:36px;height:36px;border-radius:50%;background:#3A5AB0;
                  display:flex;align-items:center;justify-content:center;
                  font-size:10px;font-weight:800;color:white;flex-shrink:0;">W2~3</div>
      <div style="width:2px;flex:1;background:rgba(91,124,246,0.2);min-height:56px;margin-top:4px;"></div>
    </div>
    <div style="padding-top:6px;padding-bottom:20px;">
      <div style="font-size:15px;font-weight:800;color:#7B9BF7;margin-bottom:8px;">
        Week 2~3 <span style="font-size:11px;font-weight:600;background:rgba(91,124,246,0.12);
        color:#7B9BF7;border:1px solid rgba(91,124,246,0.25);padding:2px 8px;border-radius:20px;margin-left:6px;">스프린트 내</span>
      </div>
      <div style="display:flex;flex-direction:column;gap:6px;">
        <div style="display:flex;align-items:center;gap:8px;">
          <span style="font-size:11px;font-weight:700;background:rgba(240,164,41,0.1);color:#C89030;
                       border:1px solid rgba(240,164,41,0.25);padding:2px 8px;border-radius:4px;flex-shrink:0;">W-01~06</span>
          <span style="font-size:13px;color:#C8D0F0;">다크모드 · 채팅 · 구독 · 초대 · 알림 · 온보딩</span>
        </div>
        <div style="display:flex;align-items:center;gap:8px;">
          <span style="font-size:11px;font-weight:700;background:rgba(240,164,41,0.1);color:#C89030;
                       border:1px solid rgba(240,164,41,0.25);padding:2px 8px;border-radius:4px;flex-shrink:0;">W-07~12</span>
          <span style="font-size:13px;color:#C8D0F0;">장바구니 · 쿠폰 · 탈퇴 · 만료 · 사진 · 대용량</span>
        </div>
      </div>
    </div>
  </div>
  <div style="display:flex;gap:0;">
    <div style="display:flex;flex-direction:column;align-items:center;margin-right:16px;">
      <div style="width:36px;height:36px;border-radius:50%;background:#1E7050;
                  display:flex;align-items:center;justify-content:center;
                  font-size:10px;font-weight:800;color:white;flex-shrink:0;">출시</div>
    </div>
    <div style="padding-top:6px;">
      <div style="font-size:15px;font-weight:800;color:#2EC88E;margin-bottom:8px;">
        출시 전 <span style="font-size:11px;font-weight:600;background:rgba(46,200,142,0.1);
        color:#2EC88E;border:1px solid rgba(46,200,142,0.25);padding:2px 8px;border-radius:20px;margin-left:6px;">참고</span>
      </div>
      <div style="display:flex;align-items:center;gap:8px;">
        <span style="font-size:11px;font-weight:700;background:rgba(46,200,142,0.1);color:#2EC88E;
                     border:1px solid rgba(46,200,142,0.2);padding:2px 8px;border-radius:4px;flex-shrink:0;">R-01~06</span>
        <span style="font-size:13px;color:#C8D0F0;">확인 및 백로그 등록</span>
      </div>
    </div>
  </div>
</div>
"""

FORM_HTML = """
<div style="margin:16px 0 24px;background:#13161F;border:1px solid rgba(255,255,255,0.08);
            border-radius:10px;overflow:hidden;">
  <div style="padding:12px 20px;background:rgba(91,124,246,0.08);
              border-bottom:1px solid rgba(255,255,255,0.06);">
    <span style="font-size:11px;font-weight:700;text-transform:uppercase;
                 letter-spacing:.1em;color:#5B7CF6;">결정 기록 양식</span>
  </div>
  <div style="display:flex;flex-direction:column;">
    <div style="display:flex;align-items:stretch;border-bottom:1px solid rgba(255,255,255,0.05);">
      <div style="width:130px;padding:14px 20px;font-size:12px;font-weight:700;color:#6B7290;
                  background:rgba(255,255,255,0.02);flex-shrink:0;display:flex;align-items:center;
                  border-right:1px solid rgba(255,255,255,0.05);">항목</div>
      <div style="padding:14px 20px;font-size:13px;color:#7B9BF7;font-weight:600;
                  font-family:'SF Mono','Fira Code',monospace;">B-01 &nbsp;/&nbsp; W-01 &nbsp;/&nbsp; R-01 등</div>
    </div>
    <div style="display:flex;align-items:stretch;border-bottom:1px solid rgba(255,255,255,0.05);">
      <div style="width:130px;padding:14px 20px;font-size:12px;font-weight:700;color:#6B7290;
                  background:rgba(255,255,255,0.02);flex-shrink:0;display:flex;align-items:center;
                  border-right:1px solid rgba(255,255,255,0.05);">결정 내용</div>
      <div style="padding:14px 20px;font-size:13px;color:#3E4560;font-style:italic;">작성 예: 매직링크 단독 인증으로 확정</div>
    </div>
    <div style="display:flex;align-items:stretch;border-bottom:1px solid rgba(255,255,255,0.05);">
      <div style="width:130px;padding:14px 20px;font-size:12px;font-weight:700;color:#6B7290;
                  background:rgba(255,255,255,0.02);flex-shrink:0;display:flex;align-items:center;
                  border-right:1px solid rgba(255,255,255,0.05);">결정자</div>
      <div style="padding:14px 20px;font-size:13px;color:#3E4560;font-style:italic;">작성 예: Product Owner 홍길동</div>
    </div>
    <div style="display:flex;align-items:stretch;border-bottom:1px solid rgba(255,255,255,0.05);">
      <div style="width:130px;padding:14px 20px;font-size:12px;font-weight:700;color:#6B7290;
                  background:rgba(255,255,255,0.02);flex-shrink:0;display:flex;align-items:center;
                  border-right:1px solid rgba(255,255,255,0.05);">결정 일시</div>
      <div style="padding:14px 20px;font-size:13px;color:#3E4560;font-style:italic;">작성 예: 2026-07-05 14:00</div>
    </div>
    <div style="display:flex;align-items:stretch;">
      <div style="width:130px;padding:14px 20px;font-size:12px;font-weight:700;color:#6B7290;
                  background:rgba(255,255,255,0.02);flex-shrink:0;display:flex;align-items:center;
                  border-right:1px solid rgba(255,255,255,0.05);">PRD 반영 위치</div>
      <div style="padding:14px 20px;font-size:13px;color:#3E4560;font-style:italic;">작성 예: prd_output.md &gt; C14 &gt; 확정 요구사항</div>
    </div>
  </div>
</div>
"""

def preprocess(text: str) -> str:
    # 우선순위 판단 매트릭스
    text = re.sub(r"```\n\s*높음 ┌.*?```", MATRIX_HTML, text, flags=re.DOTALL)
    # 의사결정 일정 제안
    text = re.sub(r"```\nWeek 1 \(즉시\).*?```", SCHEDULE_HTML, text, flags=re.DOTALL)
    # 결정 기록 양식
    text = re.sub(r"```\n항목: \[B-01.*?```", FORM_HTML, text, flags=re.DOTALL)

    lines = text.split("\n")
    out = []
    for line in lines:
        # h2 앞에 앵커 div 삽입
        m2 = re.match(r"^## (.+)", line)
        if m2:
            slug = heading_to_id(m2.group(1))
            out.append(f'<div id="{slug}" style="scroll-margin-top:80px;"></div>')

        # [TODO] 뱃지
        line = re.sub(
            r"\[TODO\]",
            '<span style="display:inline-flex;align-items:center;gap:4px;background:rgba(240,164,41,0.15);'
            'color:#F0A429;border:1px solid rgba(240,164,41,0.35);padding:1px 8px;border-radius:4px;'
            'font-size:11px;font-weight:700;letter-spacing:.05em;vertical-align:middle;">TODO</span>',
            line,
        )
        # [CONFLICT] 뱃지
        line = re.sub(
            r"\[CONFLICT\]",
            '<span style="display:inline-flex;align-items:center;gap:4px;background:rgba(232,84,84,0.15);'
            'color:#E85454;border:1px solid rgba(232,84,84,0.35);padding:1px 8px;border-radius:4px;'
            'font-size:11px;font-weight:700;letter-spacing:.05em;vertical-align:middle;">CONFLICT</span>',
            line,
        )
        # P1 / P2 / P3
        line = re.sub(r"\*\*P1\*\*",
            '<span style="background:rgba(240,180,41,0.18);color:#F0B429;border:1px solid rgba(240,180,41,0.4);'
            'padding:2px 10px;border-radius:5px;font-size:12px;font-weight:800;letter-spacing:.04em;">P1</span>', line)
        line = re.sub(r"\*\*P2\*\*",
            '<span style="background:rgba(91,124,246,0.12);color:#7B9BF7;border:1px solid rgba(91,124,246,0.3);'
            'padding:2px 10px;border-radius:5px;font-size:12px;font-weight:800;letter-spacing:.04em;">P2</span>', line)
        line = re.sub(r"\*\*P3\*\*",
            '<span style="background:rgba(100,100,120,0.15);color:#6B7290;border:1px solid rgba(100,100,120,0.3);'
            'padding:2px 10px;border-radius:5px;font-size:12px;font-weight:800;letter-spacing:.04em;">P3</span>', line)
        out.append(line)
    return "\n".join(out)


# ── CSS ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
[data-testid="stAppViewContainer"] { background:#0B0D14; }
[data-testid="stHeader"]           { background:transparent; }
section.main .block-container      { padding-top:20px; padding-bottom:60px; max-width:900px; }

[data-testid="stSidebar"] {
    background: #0F111A;
    border-right: 1px solid rgba(255,255,255,0.06);
}
[data-testid="stSidebar"] * { color:#CDD2E8 !important; }
[data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] { gap:4px; }
[data-testid="stSidebar"] [data-testid="stRadio"] label {
    display:flex; align-items:center;
    padding:10px 14px; border-radius:8px;
    font-size:13px !important; font-weight:500 !important;
    border:1px solid transparent; transition:all .15s;
}
[data-testid="stSidebar"] [data-testid="stRadio"] label:hover {
    background:rgba(91,124,246,0.1); border-color:rgba(91,124,246,0.2);
}

/* TOC 버튼 */
[data-testid="stSidebar"] [data-testid="stButton"] button {
    background: transparent !important;
    border: none !important;
    color: #5A6280 !important;
    font-size: 12px !important;
    font-weight: 500 !important;
    padding: 4px 8px !important;
    text-align: left !important;
    width: 100% !important;
    border-radius: 6px !important;
    transition: all .15s !important;
}
[data-testid="stSidebar"] [data-testid="stButton"] button:hover {
    background: rgba(91,124,246,0.08) !important;
    color: #9BAAE8 !important;
}

[data-testid="stMarkdownContainer"] { font-family: -apple-system, sans-serif; line-height:1.85; }

[data-testid="stMarkdownContainer"] h1 {
    font-size:26px; font-weight:900; color:#ECEFFE;
    letter-spacing:-0.03em; border-bottom:2px solid #5B7CF6;
    padding-bottom:12px; margin:0 0 24px;
}
[data-testid="stMarkdownContainer"] h2 {
    font-size:22px; font-weight:800; color:#7EB8F7;
    margin:40px 0 12px; padding:10px 18px;
    background:rgba(91,124,246,0.08); border-left:4px solid #5B7CF6;
    border-radius:0 6px 6px 0; letter-spacing:-0.01em; font-style:italic;
}
[data-testid="stMarkdownContainer"] h3 {
    font-size:17px; font-weight:700; color:#F0C060;
    letter-spacing:0.06em; margin:28px 0 10px;
    display:flex; align-items:center; gap:6px;
}
[data-testid="stMarkdownContainer"] h3::after {
    content:''; flex:1; height:1px;
    background:rgba(240,192,96,0.2); margin-left:8px;
}
[data-testid="stMarkdownContainer"] h4 {
    font-size:16px; font-weight:600; color:#88D8B0;
    margin:18px 0 8px; font-style:italic;
}
[data-testid="stMarkdownContainer"] p  { color:#8F97B8; font-size:14px; line-height:1.85; margin-bottom:10px; }
[data-testid="stMarkdownContainer"] li { color:#8F97B8; font-size:14px; line-height:1.8; margin-bottom:4px; }
[data-testid="stMarkdownContainer"] strong { color:#CDD2E8; font-weight:700; }
[data-testid="stMarkdownContainer"] em    { color:#A0A8C8; font-style:italic; }

[data-testid="stMarkdownContainer"] code {
    font-family:'SF Mono','Fira Code',monospace;
    background:#1A1D2E; color:#7B9BF7;
    padding:2px 7px; border-radius:4px; font-size:12px;
    border:1px solid rgba(91,124,246,0.15);
}
[data-testid="stMarkdownContainer"] pre {
    background:#131624 !important; border:1px solid rgba(91,124,246,0.12);
    border-radius:10px; padding:20px 24px !important; margin:16px 0; overflow-x:auto;
}
[data-testid="stMarkdownContainer"] pre code {
    background:transparent; border:none; color:#9BAAE8; font-size:12.5px; line-height:1.75;
}
[data-testid="stMarkdownContainer"] blockquote {
    border-left:4px solid #E85454; background:rgba(232,84,84,0.06);
    padding:14px 20px; border-radius:0 8px 8px 0; margin:16px 0;
}
[data-testid="stMarkdownContainer"] blockquote p  { color:#C87070; font-size:13px; margin-bottom:4px; }
[data-testid="stMarkdownContainer"] blockquote strong { color:#E89090; }

[data-testid="stMarkdownContainer"] table { width:100%; border-collapse:collapse; margin:16px 0; font-size:13px; }
[data-testid="stMarkdownContainer"] thead tr { background:#161924; }
[data-testid="stMarkdownContainer"] th {
    color:#5B7CF6; font-size:11px; font-weight:700;
    text-transform:uppercase; letter-spacing:0.09em;
    padding:11px 16px; border:1px solid rgba(255,255,255,0.06); text-align:left;
}
[data-testid="stMarkdownContainer"] td {
    color:#8F97B8; padding:10px 16px;
    border:1px solid rgba(255,255,255,0.04); line-height:1.6;
}
[data-testid="stMarkdownContainer"] tbody tr:nth-child(even) td { background:rgba(255,255,255,0.015); }
[data-testid="stMarkdownContainer"] tbody tr:hover td {
    background:rgba(91,124,246,0.06); color:#CDD2E8; transition:all .12s;
}
[data-testid="stMarkdownContainer"] td strong { color:#CDD2E8; }
[data-testid="stMarkdownContainer"] hr { border:none; border-top:1px solid rgba(255,255,255,0.06); margin:32px 0; }

[data-testid="stDownloadButton"] button {
    background:linear-gradient(135deg,#5B7CF6,#4A6AE0) !important;
    color:white !important; border:none !important; border-radius:8px !important;
    font-weight:600 !important; font-size:13px !important;
}

.prd-eyebrow { font-size:10px; text-transform:uppercase; letter-spacing:.14em; color:#5B7CF6; font-weight:700; margin-bottom:6px; }
.prd-title   { font-size:28px; font-weight:900; letter-spacing:-.03em; color:#ECEFFE; margin:0 0 8px; }
.prd-meta    { font-size:12px; color:#3E4560; }
.chip-row    { display:flex; gap:8px; flex-wrap:wrap; margin:16px 0 24px; }
.chip        { display:inline-flex; align-items:center; gap:5px; padding:5px 12px; border-radius:20px; font-size:12px; font-weight:700; font-variant-numeric:tabular-nums; }
.chip-b { background:rgba(91,124,246,.12); color:#7B9BF7; border:1px solid rgba(91,124,246,.25); }
.chip-w { background:rgba(240,164,41,.1);  color:#C89030; border:1px solid rgba(240,164,41,.25); }
.chip-r { background:rgba(232,84,84,.1);   color:#C85050; border:1px solid rgba(232,84,84,.25); }
.chip-g { background:rgba(46,200,142,.1);  color:#2AAF7A; border:1px solid rgba(46,200,142,.25); }

/* ── Expander (케이스 토글) ── */
[data-testid="stExpander"] {
    background: #141720 !important;
    border: 1px solid rgba(255,255,255,0.07) !important;
    border-radius: 10px !important;
    margin-bottom: 8px !important;
    overflow: hidden;
}
[data-testid="stExpander"]:hover {
    border-color: rgba(91,124,246,0.3) !important;
}
[data-testid="stExpander"] summary {
    padding: 14px 18px !important;
    background: transparent !important;
    cursor: pointer;
}
[data-testid="stExpander"] summary:hover {
    background: rgba(91,124,246,0.05) !important;
}
[data-testid="stExpander"] summary p,
[data-testid="stExpander"] summary span {
    font-size: 14px !important;
    font-weight: 600 !important;
    color: #C8D0F0 !important;
}
[data-testid="stExpander"] [data-testid="stExpanderDetails"] {
    padding: 4px 18px 18px !important;
    border-top: 1px solid rgba(255,255,255,0.06) !important;
    background: rgba(0,0,0,0.15) !important;
}
</style>
""", unsafe_allow_html=True)

# ── 세션 상태 초기화 ──────────────────────────────────────────────────
if "scroll_to" not in st.session_state:
    st.session_state["scroll_to"] = None

# ── 사이드바 ──────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style='padding:16px 0 16px;border-bottom:1px solid rgba(255,255,255,0.06);margin-bottom:20px;'>
        <div style='font-size:9px;text-transform:uppercase;letter-spacing:.12em;color:#5B7CF6;font-weight:700;margin-bottom:5px;'>SecondBoost</div>
        <div style='font-size:17px;font-weight:800;color:#ECEFFE;letter-spacing:-.02em;'>PRD 문서 뷰어</div>
        <div style='font-size:11px;color:#3E4560;margin-top:4px;'>비정형 요구사항 파이프라인</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<div style='font-size:10px;color:#3E4560;text-transform:uppercase;letter-spacing:.1em;font-weight:700;margin-bottom:8px;'>문서 선택</div>", unsafe_allow_html=True)
    selected = st.radio("", list(DOCS.keys()), label_visibility="collapsed")

    st.markdown("""
    <div style='margin-top:28px;padding-top:20px;border-top:1px solid rgba(255,255,255,0.06);'>
        <div style='font-size:10px;color:#3E4560;text-transform:uppercase;letter-spacing:.1em;font-weight:700;margin-bottom:14px;'>파이프라인 현황</div>
    </div>
    """, unsafe_allow_html=True)

    for label, val, color in [("케이스 분석","15","#7B9BF7"),("TODO 항목","33","#C89030"),("Conflict","2","#C85050"),("의사결정","21","#2AAF7A")]:
        st.markdown(f"""
        <div style='display:flex;justify-content:space-between;align-items:center;
                    padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.04);'>
            <span style='font-size:12px;color:#5A6280;'>{label}</span>
            <span style='font-size:16px;font-weight:800;color:{color};font-variant-numeric:tabular-nums;'>{val}</span>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("""
    <div style='margin-top:24px;padding:14px;background:rgba(255,255,255,0.02);
                border:1px solid rgba(255,255,255,0.05);border-radius:8px;'>
        <div style='font-size:10px;color:#3E4560;text-transform:uppercase;letter-spacing:.1em;font-weight:700;margin-bottom:12px;'>의사결정 분류</div>
        <div style='display:flex;flex-direction:column;gap:8px;'>
            <div style='display:flex;align-items:center;justify-content:space-between;'>
                <div style='display:flex;align-items:center;gap:8px;'>
                    <span style='width:8px;height:8px;border-radius:50%;background:#E85454;display:inline-block;'></span>
                    <span style='font-size:12px;color:#5A6280;'>Blocker</span>
                </div>
                <span style='font-size:14px;font-weight:800;color:#E85454;'>3</span>
            </div>
            <div style='display:flex;align-items:center;justify-content:space-between;'>
                <div style='display:flex;align-items:center;gap:8px;'>
                    <span style='width:8px;height:8px;border-radius:50%;background:#F0A429;display:inline-block;'></span>
                    <span style='font-size:12px;color:#5A6280;'>주의</span>
                </div>
                <span style='font-size:14px;font-weight:800;color:#F0A429;'>12</span>
            </div>
            <div style='display:flex;align-items:center;justify-content:space-between;'>
                <div style='display:flex;align-items:center;gap:8px;'>
                    <span style='width:8px;height:8px;border-radius:50%;background:#2EC88E;display:inline-block;'></span>
                    <span style='font-size:12px;color:#5A6280;'>참고</span>
                </div>
                <span style='font-size:14px;font-weight:800;color:#2EC88E;'>6</span>
            </div>
        </div>
        <div style='display:flex;height:4px;border-radius:4px;overflow:hidden;margin-top:14px;gap:2px;'>
            <div style='width:14.3%;background:#E85454;border-radius:2px;'></div>
            <div style='width:57.1%;background:#F0A429;border-radius:2px;'></div>
            <div style='width:28.6%;background:#2EC88E;border-radius:2px;'></div>
        </div>
    </div>
    """, unsafe_allow_html=True)

# ── 콘텐츠 로드 ───────────────────────────────────────────────────────
fname, loader, content_fn = DOCS[selected]
content = loader(fname) if loader else content_fn()
processed = preprocess(content)

# ── TOC 사이드바 (문서 내 목차) ───────────────────────────────────────
toc = extract_toc(content, max_level=2)
if toc:
    with st.sidebar:
        st.markdown("""
        <div style='margin-top:20px;padding-top:16px;border-top:1px solid rgba(255,255,255,0.06);'>
            <div style='font-size:10px;color:#3E4560;text-transform:uppercase;
                        letter-spacing:.1em;font-weight:700;margin-bottom:8px;'>목차</div>
        </div>
        """, unsafe_allow_html=True)

        for level, display, slug in toc:
            indent = "　" if level == 3 else ""
            label = f"{indent}{display[:28]}{'…' if len(display)>28 else ''}"
            if st.button(label, key=f"toc_{slug}"):
                st.session_state["scroll_to"] = slug

# ── 본문 헤더 ─────────────────────────────────────────────────────────
col_title, col_dl = st.columns([5, 1])
with col_title:
    st.markdown(f"""
    <div class='prd-eyebrow'>SecondBoost · PRD 파이프라인</div>
    <div class='prd-title'>{selected}</div>
    <div class='prd-meta'>{fname} &nbsp;·&nbsp; {len(content.splitlines()):,}줄 &nbsp;·&nbsp; {len(content):,}자</div>
    <div class='chip-row'>
        <span class='chip chip-b'>케이스 15</span>
        <span class='chip chip-w'>TODO 33</span>
        <span class='chip chip-r'>Conflict 2</span>
        <span class='chip chip-g'>의사결정 21</span>
    </div>
    """, unsafe_allow_html=True)
with col_dl:
    st.markdown("<div style='padding-top:38px;'>", unsafe_allow_html=True)
    st.download_button(
        label="⬇️ 다운로드",
        data=content.encode("utf-8"),
        file_name=fname,
        mime="text/markdown",
        use_container_width=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)

st.markdown("<hr style='border:none;border-top:1px solid rgba(255,255,255,0.06);margin:4px 0 28px;'>", unsafe_allow_html=True)

# ── 본문 렌더링 ───────────────────────────────────────────────────────
P_COLOR  = {"P1": "#F0B429", "P2": "#7B9BF7", "P3": "#6B7290"}
P_BG     = {"P1": "rgba(240,180,41,0.14)", "P2": "rgba(91,124,246,0.12)", "P3": "rgba(100,100,120,0.12)"}
P_BORDER = {"P1": "rgba(240,180,41,0.35)", "P2": "rgba(91,124,246,0.28)", "P3": "rgba(100,100,120,0.28)"}
SRC_ICON = {"Slack DM": "S", "Slack Channel Thread": "S", "CS 이메일": "E",
            "Meeting": "M", "Mixed": "!", "복합": "!"}
SRC_COLOR = {"S": "#7B9BF7", "E": "#C89030", "M": "#2AAF7A", "!": "#C85050"}

if has_decisions(content):
    preamble, groups = parse_decisions(content)

    if preamble.strip():
        st.markdown(preprocess(preamble), unsafe_allow_html=True)

    for tier_key, tier_intro, items in groups:
        tier = DECISION_TIERS[tier_key]

        # 티어 헤더
        st.markdown(f"""
        <div style='display:flex;align-items:center;gap:10px;
                    margin:32px 0 12px;padding:12px 18px;
                    background:{tier["bg"]};border-left:4px solid {tier["color"]};
                    border-radius:0 8px 8px 0;'>
            <span style='font-size:18px;font-weight:800;color:{tier["color"]};'>{tier["label"]}</span>
            <span style='font-size:12px;color:{tier["color"]};opacity:.7;margin-left:auto;
                         font-weight:600;'>{len(items)}건</span>
        </div>
        """, unsafe_allow_html=True)

        if not items:
            # 참고처럼 표 형태인 경우 그냥 렌더링
            st.markdown(preprocess(tier_intro), unsafe_allow_html=True)
            continue

        for code, title, case_ref, impact, urgency, item_content in items:
            label = f"{code}  ·  {title}" + (f"  ({case_ref})" if case_ref else "")

            with st.expander(label, expanded=False):
                # 메타 배지 행
                badges = []
                if case_ref:
                    is_conflict = "Conflict" in case_ref or "conflict" in case_ref
                    case_color = "#E85454" if is_conflict else "#7B9BF7"
                    case_bg    = "rgba(232,84,84,0.12)" if is_conflict else "rgba(91,124,246,0.1)"
                    badges.append(
                        f'<span style="font-size:11px;font-weight:700;background:{case_bg};'
                        f'color:{case_color};border:1px solid {case_color}40;'
                        f'padding:2px 9px;border-radius:4px;">📎 {case_ref}</span>'
                    )
                if urgency:
                    badges.append(
                        f'<span style="font-size:11px;font-weight:600;background:rgba(255,255,255,0.04);'
                        f'color:#8B91A8;border:1px solid rgba(255,255,255,0.08);'
                        f'padding:2px 9px;border-radius:4px;">⏱ {urgency[:40]}</span>'
                    )

                st.markdown(f"""
                <div style='padding:12px 0 14px;'>
                    <div style='font-size:17px;font-weight:800;color:{tier["color"]};
                                margin-bottom:6px;'>{code}. {title}</div>
                    {"<div style='display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px;'>" + "".join(badges) + "</div>" if badges else ""}
                    {"<div style='font-size:13px;color:#8F97B8;line-height:1.7;padding:8px 12px;background:rgba(255,255,255,0.02);border-radius:6px;border-left:3px solid rgba(255,255,255,0.08);'>" + impact + "</div>" if impact else ""}
                </div>
                <hr style='border:none;border-top:1px solid rgba(255,255,255,0.05);margin:4px 0 12px;'>
                """, unsafe_allow_html=True)

                st.markdown(preprocess(item_content), unsafe_allow_html=True)

elif has_cases(content):
    preamble, cases = parse_cases(content)

    # 전문 (케이스 전 소개글)
    if preamble.strip():
        st.markdown(preprocess(preamble), unsafe_allow_html=True)

    # 케이스 개수 표시
    st.markdown(f"""
    <div style='font-size:11px;text-transform:uppercase;letter-spacing:.1em;
                color:#3E4560;font-weight:700;margin-bottom:12px;'>
        케이스 목록 — {len(cases)}건
    </div>""", unsafe_allow_html=True)

    for num, feature, type_, priority, conflict, case_content in cases:
        pc = P_COLOR.get(priority, "#7B9BF7")
        pb = P_BG.get(priority, "rgba(91,124,246,0.12)")
        pbr = P_BORDER.get(priority, "rgba(91,124,246,0.28)")

        src_key = SRC_ICON.get(type_, "")
        src_color = SRC_COLOR.get(src_key, "#5A6280")

        conflict_badge = (
            ' <span style="font-size:10px;font-weight:700;background:rgba(232,84,84,0.15);'
            'color:#E85454;border:1px solid rgba(232,84,84,0.3);padding:1px 7px;'
            'border-radius:4px;margin-left:4px;vertical-align:middle;">CONFLICT</span>'
            if conflict else ""
        )

        label = (
            f"C{num}  ·  {feature}"
            + ("  ⚡ CONFLICT" if conflict else "")
            + f"  [{priority}]"
        )

        with st.expander(label, expanded=False):
            # 케이스 메타 헤더
            st.markdown(f"""
            <div style='display:flex;align-items:center;gap:10px;
                        padding:10px 0 16px;flex-wrap:wrap;'>
                <span style='font-size:13px;font-weight:800;color:#ECEFFE;
                             font-variant-numeric:tabular-nums;'>C{num}</span>
                <span style='font-size:15px;font-weight:700;color:#CDD2E8;'>{feature}</span>
                <span style='margin-left:auto;display:flex;gap:8px;align-items:center;'>
                    {"<span style='font-size:11px;font-weight:700;background:" + pb + ";color:" + pc + ";border:1px solid " + pbr + ";padding:2px 10px;border-radius:5px;'>" + priority + "</span>" if priority else ""}
                    {"<span style='font-size:11px;font-weight:700;background:rgba(91,124,246,0.1);color:" + src_color + ";padding:2px 8px;border-radius:4px;'>" + type_ + "</span>" if type_ else ""}
                    {('<span style="font-size:11px;font-weight:700;background:rgba(232,84,84,0.15);color:#E85454;border:1px solid rgba(232,84,84,0.3);padding:2px 8px;border-radius:4px;">⚡ CONFLICT</span>' if conflict else "")}
                </span>
            </div>
            <hr style='border:none;border-top:1px solid rgba(255,255,255,0.05);margin:0 0 12px;'>
            """, unsafe_allow_html=True)

            st.markdown(preprocess(case_content), unsafe_allow_html=True)
else:
    # 케이스 없는 문서는 기존 방식으로 렌더링
    st.markdown(processed, unsafe_allow_html=True)

# ── 스크롤 JS 실행 ────────────────────────────────────────────────────
scroll_target = st.session_state.get("scroll_to")
if scroll_target:
    components.html(f"""
    <script>
      var el = window.parent.document.getElementById("{scroll_target}");
      if (el) {{
        el.scrollIntoView({{behavior: "smooth", block: "start"}});
      }}
    </script>
    """, height=0)
    st.session_state["scroll_to"] = None
