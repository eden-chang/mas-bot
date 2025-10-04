#!/bin/bash

# 마스토돈 툿 삭제 봇 사용 예시 스크립트

echo "🤖 마스토돈 툿 삭제 봇 사용 예시"
echo "================================="

# 환경 변수에서 토큰 읽기 (보안을 위해)
if [ -z "$MASTODON_ACCESS_TOKEN" ]; then
    echo "❌ MASTODON_ACCESS_TOKEN 환경 변수가 설정되지 않았습니다."
    echo "다음과 같이 설정하세요:"
    echo "export MASTODON_ACCESS_TOKEN='your_access_token_here'"
    exit 1
fi

echo "📝 사용 가능한 옵션들:"
echo ""

echo "1️⃣  드라이런 (삭제 미리보기)"
echo "python main.py --token \$MASTODON_ACCESS_TOKEN --dry-run"
echo ""

echo "2️⃣  기본 삭제 (확인 프롬프트 포함)"
echo "python main.py --token \$MASTODON_ACCESS_TOKEN"
echo ""

echo "3️⃣  확인 없이 바로 삭제"
echo "python main.py --token \$MASTODON_ACCESS_TOKEN --confirm"
echo ""

echo "4️⃣  다른 인스턴스 사용"
echo "python main.py --token \$MASTODON_ACCESS_TOKEN --instance https://mastodon.world"
echo ""

echo "⚠️  주의: 먼저 드라이런으로 테스트하는 것을 권장합니다!"
echo ""

read -p "실행할 옵션 번호를 선택하세요 (1-4, 0=종료): " choice

case $choice in
    1)
        echo "🔍 드라이런 실행 중..."
        python main.py --token "$MASTODON_ACCESS_TOKEN" --dry-run
        ;;
    2)
        echo "🚀 기본 삭제 실행 중..."
        python main.py --token "$MASTODON_ACCESS_TOKEN"
        ;;
    3)
        echo "⚡ 즉시 삭제 실행 중..."
        echo "⚠️  정말로 모든 툿을 삭제하시겠습니까? (y/N)"
        read -p "확인: " confirm
        if [[ $confirm =~ ^[Yy]$ ]]; then
            python main.py --token "$MASTODON_ACCESS_TOKEN" --confirm
        else
            echo "❌ 취소되었습니다."
        fi
        ;;
    4)
        read -p "인스턴스 URL을 입력하세요 (예: https://mastodon.world): " instance
        if [ -n "$instance" ]; then
            echo "🌐 사용자 지정 인스턴스로 실행 중..."
            python main.py --token "$MASTODON_ACCESS_TOKEN" --instance "$instance" --dry-run
        else
            echo "❌ 인스턴스 URL이 입력되지 않았습니다."
        fi
        ;;
    0)
        echo "👋 종료합니다."
        ;;
    *)
        echo "❌ 올바르지 않은 선택입니다."
        ;;
esac
