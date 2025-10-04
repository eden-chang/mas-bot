"""
마스토돈 툿 일괄 삭제 봇
지정된 계정의 모든 툿을 10개씩 배치로 삭제합니다.
"""

import os
import sys
import time
import json
from datetime import datetime
from typing import List, Dict, Optional, Any
import argparse
import pytz

# 마스토돈 라이브러리
try:
    from mastodon import Mastodon, MastodonError, MastodonAPIError, MastodonNetworkError
except ImportError:
    print("❌ Mastodon.py 라이브러리가 설치되지 않았습니다.")
    print("pip install Mastodon.py 를 실행하세요.")
    sys.exit(1)


class MastodonDeleteBot:
    """마스토돈 툿 일괄 삭제 봇"""
    
    def __init__(self, access_token: str, instance_url: str = "https://mastodon.social"):
        """
        MastodonDeleteBot 초기화
        
        Args:
            access_token: 마스토돈 액세스 토큰
            instance_url: 마스토돈 인스턴스 URL
        """
        self.access_token = access_token
        self.instance_url = instance_url
        self.mastodon = None
        self.batch_size = 10  # 한 번에 삭제할 툿 개수
        self.delay_between_batches = 2.0  # 배치 간 지연 시간 (초)
        self.delay_between_deletes = 0.5  # 개별 삭제 간 지연 시간 (초)
        
        # 통계
        self.stats = {
            'total_found': 0,
            'total_deleted': 0,
            'total_failed': 0,
            'start_time': None,
            'end_time': None
        }
        
        print(f"🤖 마스토돈 툿 삭제 봇 초기화 완료")
        print(f"   인스턴스: {instance_url}")
        print(f"   배치 크기: {self.batch_size}개")
    
    def initialize_client(self) -> bool:
        """마스토돈 클라이언트 초기화"""
        try:
            self.mastodon = Mastodon(
                access_token=self.access_token,
                api_base_url=self.instance_url,
                request_timeout=30
            )
            
            # 연결 테스트
            account_info = self.mastodon.me()
            username = account_info.get('username', 'unknown')
            statuses_count = account_info.get('statuses_count', 0)
            
            print(f"✅ 계정 연결 성공: @{username}")
            print(f"   현재 툿 개수: {statuses_count:,}개")
            
            self.stats['total_found'] = statuses_count
            return True
            
        except Exception as e:
            print(f"❌ 마스토돈 클라이언트 초기화 실패: {e}")
            return False
    
    def get_user_statuses(self, max_id: Optional[str] = None, limit: int = 40) -> List[Dict[str, Any]]:
        """
        사용자의 툿 목록 가져오기
        
        Args:
            max_id: 이 ID보다 이전 툿들을 가져옴
            limit: 가져올 툿 개수 (최대 40)
        
        Returns:
            툿 목록
        """
        try:
            # 자신의 계정 정보 가져오기
            account_info = self.mastodon.me()
            account_id = account_info['id']
            
            # 계정의 툿 목록 가져오기
            statuses = self.mastodon.account_statuses(
                id=account_id,
                max_id=max_id,
                limit=limit,
                exclude_replies=False,  # 답글도 포함
                exclude_reblogs=False   # 부스트도 포함
            )
            
            return statuses
            
        except Exception as e:
            print(f"❌ 툿 목록 조회 실패: {e}")
            return []
    
    def delete_status(self, status_id: str) -> bool:
        """
        특정 툿 삭제
        
        Args:
            status_id: 삭제할 툿 ID
        
        Returns:
            삭제 성공 여부
        """
        try:
            self.mastodon.status_delete(status_id)
            return True
            
        except MastodonAPIError as e:
            print(f"   ❌ API 오류로 삭제 실패 (ID: {status_id}): {e}")
            return False
            
        except Exception as e:
            print(f"   ❌ 예상치 못한 오류로 삭제 실패 (ID: {status_id}): {e}")
            return False
    
    def delete_batch(self, statuses: List[Dict[str, Any]]) -> Dict[str, int]:
        """
        툿 배치 삭제
        
        Args:
            statuses: 삭제할 툿 목록
        
        Returns:
            삭제 결과 (성공/실패 개수)
        """
        batch_result = {'success': 0, 'failed': 0}
        
        print(f"📦 배치 삭제 시작 ({len(statuses)}개 툿)")
        
        for i, status in enumerate(statuses, 1):
            status_id = status['id']
            created_at = status['created_at']
            content = status['content']
            
            # 내용 미리보기 (HTML 태그 제거 및 길이 제한)
            preview = self.clean_content(content)[:50]
            if len(content) > 50:
                preview += "..."
            
            print(f"   [{i:2d}/{len(statuses)}] 삭제 중: {created_at.strftime('%Y-%m-%d %H:%M')} - {preview}")
            
            if self.delete_status(status_id):
                batch_result['success'] += 1
                print(f"   ✅ 삭제 성공")
            else:
                batch_result['failed'] += 1
            
            # 개별 삭제 간 지연
            if i < len(statuses):
                time.sleep(self.delay_between_deletes)
        
        return batch_result
    
    def clean_content(self, html_content: str) -> str:
        """HTML 태그를 제거하고 텍스트만 추출"""
        try:
            # 간단한 HTML 태그 제거
            import re
            clean_text = re.sub(r'<[^>]+>', '', html_content)
            # 연속된 공백을 하나로 압축
            clean_text = re.sub(r'\s+', ' ', clean_text).strip()
            return clean_text
        except:
            return html_content[:50]
    
    def delete_all_statuses(self, confirm: bool = False, dry_run: bool = False) -> None:
        """
        모든 툿 삭제
        
        Args:
            confirm: 삭제 확인 여부
            dry_run: 실제 삭제하지 않고 미리보기만
        """
        if not self.initialize_client():
            return
        
        if not confirm and not dry_run:
            print("\n⚠️  주의: 이 작업은 되돌릴 수 없습니다!")
            print("모든 툿을 삭제하시겠습니까? 확인하려면 'DELETE_ALL'을 입력하세요:")
            
            user_input = input().strip()
            if user_input != "DELETE_ALL":
                print("❌ 삭제가 취소되었습니다.")
                return
        
        if dry_run:
            print("\n🔍 드라이런 모드: 실제로 삭제하지 않고 미리보기만 표시합니다.")
        
        self.stats['start_time'] = datetime.now(pytz.timezone('Asia/Seoul'))
        
        print(f"\n🚀 툿 삭제 시작 - {self.stats['start_time'].strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)
        
        max_id = None
        batch_count = 0
        
        while True:
            # 툿 목록 가져오기
            statuses = self.get_user_statuses(max_id=max_id, limit=self.batch_size)
            
            if not statuses:
                print("\n✅ 더 이상 삭제할 툿이 없습니다.")
                break
            
            batch_count += 1
            print(f"\n📦 배치 #{batch_count} 처리 중...")
            
            if dry_run:
                # 드라이런: 삭제할 툿 목록만 표시
                print(f"   삭제 예정 툿 {len(statuses)}개:")
                for i, status in enumerate(statuses, 1):
                    created_at = status['created_at']
                    content = self.clean_content(status['content'])[:50]
                    print(f"   [{i:2d}] {created_at.strftime('%Y-%m-%d %H:%M')} - {content}...")
                
                # 통계 업데이트 (드라이런)
                self.stats['total_deleted'] += len(statuses)
            else:
                # 실제 삭제
                batch_result = self.delete_batch(statuses)
                
                # 통계 업데이트
                self.stats['total_deleted'] += batch_result['success']
                self.stats['total_failed'] += batch_result['failed']
                
                print(f"   📊 배치 결과: 성공 {batch_result['success']}개, 실패 {batch_result['failed']}개")
            
            # 다음 배치를 위한 max_id 설정
            max_id = statuses[-1]['id']
            
            # 배치 간 지연
            if not dry_run:
                print(f"   ⏱️  {self.delay_between_batches}초 대기 중...")
                time.sleep(self.delay_between_batches)
        
        self.stats['end_time'] = datetime.now(pytz.timezone('Asia/Seoul'))
        
        # 최종 결과 출력
        self.print_final_report(dry_run)
    
    def print_final_report(self, dry_run: bool = False) -> None:
        """최종 결과 리포트 출력"""
        print("\n" + "=" * 60)
        print("📊 최종 결과 리포트")
        print("=" * 60)
        
        if dry_run:
            print("🔍 드라이런 결과:")
            print(f"   삭제 예정 툿: {self.stats['total_deleted']:,}개")
        else:
            print(f"✅ 삭제 완료 툿: {self.stats['total_deleted']:,}개")
            print(f"❌ 삭제 실패 툿: {self.stats['total_failed']:,}개")
            
            total_processed = self.stats['total_deleted'] + self.stats['total_failed']
            if total_processed > 0:
                success_rate = (self.stats['total_deleted'] / total_processed) * 100
                print(f"📈 성공률: {success_rate:.1f}%")
        
        if self.stats['start_time'] and self.stats['end_time']:
            duration = self.stats['end_time'] - self.stats['start_time']
            print(f"⏱️  소요 시간: {duration}")
        
        print(f"🕐 완료 시간: {self.stats['end_time'].strftime('%Y-%m-%d %H:%M:%S')}")


def main():
    """메인 함수"""
    parser = argparse.ArgumentParser(description='마스토돈 툿 일괄 삭제 봇')
    parser.add_argument('--token', required=True, help='마스토돈 액세스 토큰')
    parser.add_argument('--instance', default='https://mastodon.social', 
                       help='마스토돈 인스턴스 URL (기본값: https://mastodon.social)')
    parser.add_argument('--confirm', action='store_true', 
                       help='확인 프롬프트 없이 바로 삭제 시작')
    parser.add_argument('--dry-run', action='store_true', 
                       help='실제 삭제하지 않고 미리보기만 실행')
    
    args = parser.parse_args()
    
    print("🤖 마스토돈 툿 일괄 삭제 봇")
    print("=" * 40)
    
    # 봇 초기화
    bot = MastodonDeleteBot(
        access_token=args.token,
        instance_url=args.instance
    )
    
    try:
        # 삭제 실행
        bot.delete_all_statuses(
            confirm=args.confirm,
            dry_run=args.dry_run
        )
        
    except KeyboardInterrupt:
        print("\n\n⏹️  사용자가 중단했습니다.")
        bot.stats['end_time'] = datetime.now(pytz.timezone('Asia/Seoul'))
        bot.print_final_report()
        
    except Exception as e:
        print(f"\n❌ 예상치 못한 오류 발생: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
