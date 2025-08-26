#!/usr/bin/env python3
"""
커스텀 명령어 디버깅 스크립트
실제 Google Sheets에서 어떤 데이터가 로드되는지 확인합니다.
"""

import os
import sys

# 경로 설정
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def debug_custom_commands():
    """커스텀 명령어 데이터를 자세히 분석"""
    print("=== 커스텀 명령어 디버깅 시작 ===\n")
    
    try:
        from custom_command import get_custom_command_manager
        from utils.sheets_operations import get_sheets_manager
        from config.settings import config
        
        # 1. SheetsManager로 직접 시트 데이터 조회
        print("1. Google Sheets 직접 조회")
        sheets_manager = get_sheets_manager()
        
        try:
            worksheet_name = config.get_worksheet_name('CUSTOM') if hasattr(config, 'get_worksheet_name') else '커스텀'
            print(f"   조회할 워크시트: '{worksheet_name}'")
            
            custom_data = sheets_manager.get_worksheet_data(worksheet_name)
            print(f"   로드된 데이터: {len(custom_data)}개 행")
            
            if custom_data:
                print("\n   전체 데이터:")
                for i, row in enumerate(custom_data, 1):
                    command = str(row.get('명령어', '')).strip()
                    phrase = str(row.get('문구', '')).strip()
                    print(f"   {i}. 명령어: '{command}' | 문구: '{phrase[:50]}{'...' if len(phrase) > 50 else ''}'")
                
                # '매력' 명령어 찾기
                charm_found = False
                for row in custom_data:
                    command = str(row.get('명령어', '')).strip()
                    if '매력' in command or command.lower() == '매력':
                        print(f"\n   ✅ '매력' 관련 명령어 발견: '{command}'")
                        charm_found = True
                
                if not charm_found:
                    print("\n   ❌ '매력' 명령어가 시트에 없습니다!")
            
            else:
                print("   ⚠️ 시트에 데이터가 없습니다!")
                
        except Exception as e:
            print(f"   ❌ 시트 조회 실패: {e}")
            import traceback
            traceback.print_exc()
        
        # 2. CustomCommandManager 분석
        print(f"\n2. CustomCommandManager 분석")
        manager = get_custom_command_manager()
        
        # 정규화된 명령어들 확인
        try:
            available_commands = manager.get_available_commands()
            print(f"   사용 가능한 명령어 ({len(available_commands)}개): {available_commands}")
            
            # 각 명령어의 정규화된 형태 확인
            print(f"\n   명령어 정규화 테스트:")
            test_commands = ["매력", "매 력", "CHARM", "능력치", "YN"]
            
            for cmd in test_commands:
                normalized = manager._normalize_command(cmd)
                is_custom = manager.find_matching_command(cmd) is not None
                print(f"   '{cmd}' -> '{normalized}' -> 존재: {is_custom}")
            
            # _get_custom_commands()로 실제 내부 데이터 확인
            print(f"\n   내부 명령어 딕셔너리:")
            internal_commands = manager._get_custom_commands()
            for cmd, phrases in internal_commands.items():
                print(f"   '{cmd}': {len(phrases)}개 문구")
                for phrase in phrases[:2]:  # 처음 2개만 표시
                    print(f"      - '{phrase[:100]}{'...' if len(phrase) > 100 else ''}'")
        
        except Exception as e:
            print(f"   ❌ CustomCommandManager 분석 실패: {e}")
            import traceback
            traceback.print_exc()
        
        # 3. 라우터 통합 상태 확인
        print(f"\n3. 라우터 통합 상태 확인")
        try:
            from handlers.command_router import get_command_router
            
            router = get_command_router()
            all_commands = router.get_available_commands()
            
            custom_commands = [cmd for cmd in all_commands if cmd['category'] == '커스텀']
            print(f"   라우터에 등록된 커스텀 명령어: {len(custom_commands)}개")
            
            for cmd in custom_commands:
                print(f"   - {cmd['name']}: {cmd['description']}")
            
            # 매력 명령어 라우팅 테스트
            print(f"\n   '매력' 라우팅 직접 테스트:")
            from handlers.command_router import route_command
            
            result = route_command("debug_user", ["매력"], {"user_name": "디버그유저"})
            print(f"   라우팅 성공: {result.is_successful()}")
            print(f"   응답: {result.get_user_message()}")
            
        except Exception as e:
            print(f"   ❌ 라우터 통합 확인 실패: {e}")
            import traceback
            traceback.print_exc()
        
        # 4. 캐시 상태 확인
        print(f"\n4. 캐시 상태 확인")
        try:
            from utils.cache_manager import bot_cache
            
            cache_keys = bot_cache.general_cache.get_keys()
            custom_cache_keys = [key for key in cache_keys if 'custom' in key.lower()]
            
            print(f"   전체 캐시 키: {len(cache_keys)}개")
            print(f"   커스텀 관련 캐시 키: {custom_cache_keys}")
            
            # 캐시 무효화 테스트
            print(f"\n   캐시 무효화 테스트")
            from custom_command import invalidate_custom_command_cache
            
            cache_cleared = invalidate_custom_command_cache()
            print(f"   캐시 무효화 성공: {cache_cleared}")
            
            # 무효화 후 재조회
            available_after_clear = manager.get_available_commands()
            print(f"   캐시 클리어 후 사용 가능 명령어: {available_after_clear}")
            
        except Exception as e:
            print(f"   ❌ 캐시 상태 확인 실패: {e}")
            import traceback
            traceback.print_exc()
        
    except Exception as e:
        print(f"❌ 전체 디버깅 실패: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n=== 커스텀 명령어 디버깅 완료 ===")

def suggest_solutions():
    """해결 방안 제시"""
    print("\n=== 해결 방안 ===")
    print("1. Google Sheets 확인:")
    print("   - '커스텀' 워크시트가 있는지 확인")
    print("   - '명령어' 및 '문구' 컬럼이 있는지 확인")
    print("   - '매력' 명령어가 실제로 있는지 확인")
    print("")
    print("2. 시트 데이터 추가 (매력 명령어가 없는 경우):")
    print("   명령어: 매력")
    print("   문구: {시전자}{의} 매력은 {1d100}점입니다!")
    print("")
    print("3. 봇 재시작:")
    print("   - 시트를 수정한 후 봇을 재시작하거나")
    print("   - 15분 대기 (캐시 만료)")
    print("")
    print("4. 권한 확인:")
    print("   - Google Sheets API 권한")
    print("   - 시트 접근 권한")

if __name__ == "__main__":
    debug_custom_commands()
    suggest_solutions()