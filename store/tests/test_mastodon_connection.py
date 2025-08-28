#!/usr/bin/env python3
"""
마스토돈 연결 테스트 스크립트
"""

import os
import sys
from pathlib import Path
import logging

# 프로젝트 루트를 sys.path에 추가
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 환경 변수 로드
from config.settings import config
from utils.logging_config import logger

def test_mastodon_connection():
    """마스토돈 연결 상세 테스트"""
    print("=== 마스토돈 연결 테스트 시작 ===")
    
    try:
        # 1. 설정 정보 확인
        print(f"서버 URL: {config.MASTODON_API_BASE_URL}")
        print(f"클라이언트 ID: {config.MASTODON_CLIENT_ID[:20]}...")
        print(f"액세스 토큰: {config.MASTODON_ACCESS_TOKEN[:20]}...")
        
        # 2. mastodon 라이브러리 임포트
        try:
            import mastodon
            print("✅ mastodon 라이브러리 임포트 성공")
        except ImportError as e:
            print(f"❌ mastodon 라이브러리 임포트 실패: {e}")
            return False
        
        # 3. Mastodon API 객체 생성
        print("\n📡 API 객체 생성 중...")
        api = mastodon.Mastodon(
            client_id=config.MASTODON_CLIENT_ID,
            client_secret=config.MASTODON_CLIENT_SECRET,
            access_token=config.MASTODON_ACCESS_TOKEN,
            api_base_url=config.MASTODON_API_BASE_URL
        )
        print("✅ API 객체 생성 성공")
        
        # 4. 계정 정보 확인
        print("\n👤 계정 정보 확인 중...")
        account = api.me()
        print(f"✅ 로그인 성공: @{account.acct}")
        print(f"   표시 이름: {account.display_name}")
        print(f"   팔로워: {account.followers_count}")
        print(f"   팔로잉: {account.following_count}")
        
        # 5. 서버 정보 확인
        print("\n🌐 서버 정보 확인 중...")
        try:
            instance = api.instance()
            print(f"✅ 서버: {instance.title}")
            print(f"   버전: {instance.version}")
            print(f"   사용자 수: {instance.stats.user_count}")
        except Exception as e:
            print(f"⚠️ 서버 정보 조회 실패: {e}")
        
        # 6. 스트리밍 연결 테스트 (간단히)
        print("\n🔄 스트리밍 연결 테스트...")
        
        class TestStreamListener:
            def __init__(self):
                self.connected = False
                
            def on_update(self, status):
                print(f"📨 테스트 스트림 수신: {status.content[:50]}...")
                return True  # 연결 확인되면 종료
                
            def on_notification(self, notification):
                print(f"🔔 알림 수신: {notification.type}")
                return True  # 연결 확인되면 종료
        
        # 스트리밍 연결 시도 (매우 짧게)
        listener = TestStreamListener()
        try:
            print("   스트리밍 서버 연결 시도...")
            
            # 타임라인 스트림으로 테스트 (가장 일반적)
            stream = api.stream_user(
                listener=listener,
                timeout=10,  # 10초 타임아웃
                reconnect_async=False,
                reconnect_async_wait_sec=5
            )
            print("✅ 스트리밍 연결 테스트 완료")
            
        except mastodon.MastodonNetworkError as e:
            print(f"❌ 네트워크 오류: {e}")
            print("   - 인터넷 연결을 확인해주세요")
            print("   - 방화벽 설정을 확인해주세요")
            return False
            
        except mastodon.MastodonAPIError as e:
            print(f"❌ API 오류: {e}")
            print("   - 토큰이 유효한지 확인해주세요")
            print("   - 권한 설정을 확인해주세요")
            return False
            
        except Exception as e:
            print(f"❌ 스트리밍 연결 실패: {e}")
            print(f"   오류 타입: {type(e).__name__}")
            
            # 자세한 오류 정보
            if hasattr(e, 'response'):
                print(f"   HTTP 상태: {e.response.status_code if hasattr(e.response, 'status_code') else 'N/A'}")
                print(f"   응답 내용: {str(e.response.content)[:200] if hasattr(e.response, 'content') else 'N/A'}")
            
            return False
        
        print("\n✅ 모든 테스트 완료!")
        return True
        
    except Exception as e:
        print(f"❌ 전체 테스트 실패: {e}")
        print(f"오류 타입: {type(e).__name__}")
        
        # 더 자세한 오류 정보
        import traceback
        print("\n상세 오류 정보:")
        print(traceback.format_exc())
        
        return False

def test_streaming_endpoints():
    """스트리밍 엔드포인트별 테스트"""
    print("\n=== 스트리밍 엔드포인트 테스트 ===")
    
    try:
        import mastodon
        
        api = mastodon.Mastodon(
            client_id=config.MASTODON_CLIENT_ID,
            client_secret=config.MASTODON_CLIENT_SECRET,
            access_token=config.MASTODON_ACCESS_TOKEN,
            api_base_url=config.MASTODON_API_BASE_URL
        )
        
        endpoints = [
            ("사용자 스트림", "stream_user"),
            ("로컬 스트림", "stream_local"),
            ("공개 스트림", "stream_public"),
        ]
        
        class QuickListener:
            def on_update(self, status): return True
            def on_notification(self, notification): return True
        
        for name, method in endpoints:
            print(f"\n📡 {name} 테스트 중...")
            try:
                stream_method = getattr(api, method)
                stream_method(
                    listener=QuickListener(),
                    timeout=3,  # 3초만 테스트
                    reconnect_async=False
                )
                print(f"✅ {name} 연결 성공")
            except Exception as e:
                print(f"❌ {name} 실패: {str(e)[:100]}...")
    
    except Exception as e:
        print(f"❌ 엔드포인트 테스트 실패: {e}")

if __name__ == "__main__":
    # 로깅 레벨 설정
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s | %(levelname)-8s | %(message)s',
        datefmt='%H:%M:%S'
    )
    
    success = test_mastodon_connection()
    
    if success:
        test_streaming_endpoints()
        print("\n🎉 테스트 완료! 봇을 실행해보세요.")
    else:
        print("\n❌ 연결 테스트 실패. 설정을 확인해주세요.")