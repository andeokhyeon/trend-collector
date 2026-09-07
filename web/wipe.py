# -*- coding: utf-8 -*-
"""
회원 탈퇴 — 확인 두 번, 그리고 완전한 뒷정리. (2026-09-05 신설)

지우는 것: 추적 키워드 → 프로필(크레딧·블로그 포함) → 로그인 계정(auth).
카카오로 가입한 계정은 카카오 쪽 연결(unlink)도 끊는다 — .env에
KAKAO_ADMIN_KEY가 있을 때만 (없어도 탈퇴 자체는 완료된다).
구글은 저장해둔 토큰이 없어 서버가 대신 끊을 수 없다 — 안내만 한다.

⚠️ 순서가 중요하다: auth 계정을 먼저 지우면 프로필 조회가 막혀
   나머지를 못 지운다. 데이터부터 지우고 계정은 마지막에.
"""
import os

from uihtml import ui, render


def confirm_page(prof, tracked_count=0):
    """탈퇴 확인 화면 — 무엇이 사라지는지 숫자로 보여준다."""
    credits = int((prof or {}).get("credits") or 0)
    name = (prof or {}).get("nickname") or "회원"
    out = [render(ui.section, "회원 탈퇴", "떠나기 전에 꼭 확인해주세요")]
    out.append(
        '<div class="box wd-box">'
        f'<p class="wd-warn"><b>{name}</b>님, 탈퇴하면 아래 정보가 '
        '<b>즉시 영구 삭제</b>되며 복구할 수 없습니다.</p>'
        '<ul class="wd-list">'
        f'<li>추적 중인 키워드 <b>{tracked_count}개</b>와 그동안 쌓인 기록</li>'
        f'<li>남은 크레딧 <b>{credits:,}개</b> (환불되지 않습니다)</li>'
        '<li>등록한 블로그 주소와 계정 정보</li>'
        '<li>카카오 계정 연결 (자동 해제) · 구글 연결은 '
        '<a href="https://myaccount.google.com/connections" target="_blank" '
        'rel="noopener">구글 계정 설정</a>에서 직접 해제할 수 있습니다</li>'
        '</ul>'
        '<form method="post" action="/me/withdraw/confirm" class="wd-form" '
        'onsubmit="return this.agree.value===\'탈퇴\'">'
        '<label class="wd-label">계속하려면 아래 칸에 <b>탈퇴</b> 두 글자를 '
        '입력해주세요</label>'
        '<div class="stTextInput"><input name="agree" autocomplete="off" '
        'placeholder="탈퇴"></div>'
        '<div class="wd-btns">'
        '<a class="kh-btn" href="/me">돌아가기</a>'
        '<button class="kh-btn wd-danger" type="submit">영구 삭제하고 탈퇴</button>'
        '</div></form></div>')
    return "".join(out)


def _kakao_unlink(sb, uid):
    """카카오 쪽 연결 끊기 — 실패해도 탈퇴는 계속한다."""
    admin_key = os.environ.get("KAKAO_ADMIN_KEY", "")
    if not admin_key:
        return
    try:
        u = sb.auth.admin.get_user_by_id(uid)
        user = getattr(u, "user", u)
        for ident in (getattr(user, "identities", None) or []):
            prov = getattr(ident, "provider", "") or ""
            if prov != "kakao":
                continue
            kid = (getattr(ident, "identity_data", {}) or {}).get(
                "provider_id") or getattr(ident, "id", "")
            if not kid:
                continue
            import requests
            requests.post(
                "https://kapi.kakao.com/v1/user/unlink",
                headers={"Authorization": f"KakaoAK {admin_key}"},
                data={"target_id_type": "user_id", "target_id": str(kid)},
                timeout=5)
    except Exception:
        pass


def execute(uid):
    """탈퇴 실행. 반환: (성공 여부, 사람 말 메시지)."""
    try:
        import db
        sb = db.client()
    except Exception:
        return False, "잠시 후 다시 시도해주세요."

    _kakao_unlink(sb, uid)

    for step in (
        lambda: sb.table("tracked_keywords").delete()
                  .eq("user_id", uid).execute(),
        lambda: sb.table("profiles").delete().eq("id", uid).execute(),
    ):
        try:
            step()
        except Exception:
            pass

    try:
        sb.auth.admin.delete_user(uid)
    except Exception:
        # 계정 삭제가 실패하면 프로필만 사라진 어중간한 상태다 — 알린다.
        return False, ("데이터는 삭제됐지만 계정 정리가 끝나지 않았습니다. "
                       "고객센터로 문의해주세요.")
    return True, "탈퇴가 완료됐습니다. 그동안 이용해주셔서 감사합니다."
