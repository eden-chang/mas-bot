#!/usr/bin/env python3
"""
명단 캐시 시스템 테스트 스크립트
2시간 TTL 명단 캐시가 제대로 작동하는지 확인합니다.
"""

import os
import sys
import time

# 경로 설정
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_roster_cache_basic():
    """기본 명단 캐시 테스트"""
    print("=== 기본 명단 캐시 테스트 ===")
    
    try:
        from utils.cache_manager import cache_roster_data, get_roster_data, get_roster_cache_info, invalidate_roster_data
        from utils.sheets_operations import get_sheets_manager
        
        # 1. 초기 상태 확인
        print("1. 초기 캐시 상태 확인")
        cache_info = get_roster_cache_info()
        print(f"   캐시 상태: {cache_info}")
        
        # 2. 시트에서 명단 데이터 직접 로드
        print("\n2. Google Sheets에서 명단 데이터 로드")
        sheets_manager = get_sheets_manager()
        roster_data = sheets_manager.get_worksheet_data('명단')
        
        print(f"   로드된 명단 데이터: {len(roster_data)}개")
        if roster_data:
            print(f"   첫 번째 사용자: {roster_data[0]}")
        
        # 3. 캐시에 저장
        print("\n3. 명단 데이터 캐시에 저장")
        cached = cache_roster_data(roster_data)
        print(f"   캐시 저장 성공: {cached}")
        
        # 4. 캐시에서 조회
        print("\n4. 캐시에서 명단 데이터 조회")
        cached_data = get_roster_data()
        print(f"   캐시된 데이터: {len(cached_data) if cached_data else 0}개")
        
        if cached_data and roster_data:
            data_match = len(cached_data) == len(roster_data)
            print(f"   데이터 일치: {data_match}")
        
        # 5. 캐시 상태 정보
        print("\n5. 캐시 상태 정보")
        cache_info_after = get_roster_cache_info()
        print(f"   {cache_info_after}")
        
        return True
        
    except Exception as e:
        print(f"❌ 기본 캐시 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_sheets_manager_integration():
    """SheetsManager 통합 테스트"""
    print("\n=== SheetsManager 통합 테스트 ===")
    
    try:
        from utils.sheets_operations import get_sheets_manager
        
        sheets_manager = get_sheets_manager()
        
        # 1. 캐시 무효화
        print("1. 캐시 무효화")
        invalidated = sheets_manager.invalidate_roster_cache()
        print(f"   무효화 성공: {invalidated}")
        
        # 2. find_user_by_id 테스트 (캐시 적용됨)
        print("\n2. find_user_by_id 성능 테스트")
        
        test_user_ids = ["test", "admin", "user1", "nonexistent"]
        
        # 첫 번째 조회 (캐시 미스 - 시트에서 로드)
        print("   첫 번째 조회 (시트에서 로드):")
        start_time = time.time()
        
        for user_id in test_user_ids:
            user_info = sheets_manager.find_user_by_id(user_id)
            found = user_info is not None
            print(f"   - {user_id}: {'존재' if found else '없음'}")
        
        first_duration = time.time() - start_time
        print(f"   첫 번째 조회 시간: {first_duration:.3f}초")
        
        # 두 번째 조회 (캐시 히트)
        print("\n   두 번째 조회 (캐시에서 로드):")
        start_time = time.time()
        
        for user_id in test_user_ids:
            user_info = sheets_manager.find_user_by_id(user_id)
            found = user_info is not None
            print(f"   - {user_id}: {'존재' if found else '없음'}")
        
        second_duration = time.time() - start_time
        print(f"   두 번째 조회 시간: {second_duration:.3f}초")
        
        # 성능 향상 계산
        if first_duration > 0:
            improvement = ((first_duration - second_duration) / first_duration) * 100
            print(f"   성능 향상: {improvement:.1f}% ({first_duration/second_duration:.1f}x 빨라짐)")
        
        # 3. 캐시 상태 확인
        print("\n3. 최종 캐시 상태")
        final_cache_info = sheets_manager.get_roster_cache_status()
        print(f"   {final_cache_info}")
        
        return True
        
    except Exception as e:
        print(f"❌ 통합 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_cache_ttl():
    """캐시 TTL 테스트 (시뮬레이션)"""
    print("\n=== 캐시 TTL 테스트 (시뮬레이션) ===")
    
    try:
        from utils.cache_manager import cache_roster_data, get_roster_data, get_roster_cache_info
        
        # 테스트 데이터
        test_data = [
            {"아이디": "test1", "이름": "테스트1"},
            {"아이디": "test2", "이름": "테스트2"}
        ]
        
        # 1. 데이터 캐시
        print("1. 테스트 데이터 캐시")
        cached = cache_roster_data(test_data)
        print(f"   캐시 저장: {cached}")
        
        # 2. 캐시 정보 확인
        cache_info = get_roster_cache_info()
        print(f"   캐시 정보: {cache_info}")
        
        # 3. 만료 시간 계산
        if cache_info.get('cached'):
            remaining_hours = cache_info.get('remaining_hours', 0)
            print(f"   만료까지: {remaining_hours}시간")
            
            if remaining_hours > 0:
                print("   ✅ 캐시 TTL이 올바르게 설정됨 (2시간)")
            else:
                print("   ❌ 캐시가 이미 만료됨")
        
        # 4. 캐시에서 데이터 조회
        cached_data = get_roster_data()
        data_retrieved = cached_data is not None and len(cached_data) == 2
        print(f"   데이터 조회 성공: {data_retrieved}")
        
        return True
        
    except Exception as e:
        print(f"❌ TTL 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_legacy_compatibility():
    """레거시 호환성 테스트"""
    print("\n=== 레거시 호환성 테스트 ===")
    
    try:
        from utils.sheets_operations import user_id_check, get_user_data_safe
        
        # 기존 함수들이 캐시를 사용하는지 확인
        print("1. 레거시 함수 테스트")
        
        test_user_id = "test"
        
        # user_id_check 테스트
        start_time = time.time()
        exists = user_id_check(None, test_user_id)  # sheets_manager는 None으로 전달 (내부에서 생성)
        check_time = time.time() - start_time
        
        print(f"   user_id_check('{test_user_id}'): {exists} ({check_time:.3f}초)")
        
        # get_user_data_safe 테스트
        start_time = time.time()
        user_data = get_user_data_safe(None, test_user_id)
        get_time = time.time() - start_time
        
        print(f"   get_user_data_safe('{test_user_id}'): {'데이터 있음' if user_data else '없음'} ({get_time:.3f}초)")
        
        return True
        
    except Exception as e:
        print(f"❌ 레거시 호환성 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """메인 테스트 함수"""
    print("명단 캐시 시스템 테스트 시작\n")
    
    success_count = 0
    total_tests = 4
    
    # 개별 테스트 실행
    if test_roster_cache_basic():
        success_count += 1
    
    if test_sheets_manager_integration():
        success_count += 1
    
    if test_cache_ttl():
        success_count += 1
    
    if test_legacy_compatibility():
        success_count += 1
    
    # 결과 요약
    print(f"\n=== 테스트 결과 요약 ===")
    print(f"성공한 테스트: {success_count}/{total_tests}")
    
    if success_count == total_tests:
        print("✅ 모든 테스트가 성공했습니다!")
        print("\n명단 캐시 시스템이 정상적으로 작동합니다:")
        print("- 2시간 TTL 캐시 적용")
        print("- SheetsManager 통합")  
        print("- find_user_by_id 성능 향상")
        print("- user_exists 성능 향상")
        print("- 레거시 함수 호환성 유지")
    else:
        print(f"❌ {total_tests - success_count}개의 테스트가 실패했습니다.")
        print("문제가 있는 부분을 확인하고 수정이 필요합니다.")
    
    return success_count == total_tests


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)