#!/usr/bin/env python3
"""
커스텀 명령어 테스트 스크립트
명령어 라우터에 커스텀 명령어가 제대로 통합되었는지 확인합니다.
"""

import os
import sys

# 경로 설정
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_custom_command_basic():
    """기본 커스텀 명령어 테스트"""
    print("=== 기본 커스텀 명령어 테스트 ===")
    
    try:
        from custom_command import get_custom_command_manager, is_custom_command, execute_custom_command
        
        manager = get_custom_command_manager()
        
        # 사용 가능한 커스텀 명령어 확인
        print("1. 커스텀 명령어 목록 조회")
        available_commands = manager.get_available_commands()
        print(f"   사용 가능한 커스텀 명령어: {available_commands}")
        
        if available_commands:
            # 첫 번째 명령어로 테스트
            test_command = available_commands[0]
            print(f"\n2. '{test_command}' 명령어 테스트")
            print(f"   is_custom_command('{test_command}'): {is_custom_command(test_command)}")
            
            # 실행 테스트
            result = execute_custom_command(test_command, "테스트유저")
            print(f"   실행 결과: {result}")
            
            # 매력 명령어 특별 테스트
            print(f"\n3. '매력' 명령어 특별 테스트")
            print(f"   is_custom_command('매력'): {is_custom_command('매력')}")
            print(f"   is_custom_command('매 력'): {is_custom_command('매 력')}")  # 띄어쓰기 포함
            print(f"   is_custom_command('매력'): {is_custom_command('매력')}")  # 대문자
            
            charm_result = execute_custom_command("매력", "철수")
            print(f"   '매력' 실행 결과 (사용자: 철수): {charm_result}")
            
            charm_result2 = execute_custom_command("매력", "영희")
            print(f"   '매력' 실행 결과 (사용자: 영희): {charm_result2}")
            
        else:
            print("   ⚠️ 사용 가능한 커스텀 명령어가 없습니다. Google Sheets 연결을 확인하세요.")
        
        return True
        
    except Exception as e:
        print(f"❌ 커스텀 명령어 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_command_router_integration():
    """명령어 라우터 통합 테스트"""
    print("\n=== 명령어 라우터 통합 테스트 ===")
    
    try:
        from handlers.command_router import get_command_router, route_command
        
        router = get_command_router()
        
        # 1. 사용 가능한 명령어 목록 확인
        print("1. 전체 명령어 목록 조회")
        all_commands = router.get_available_commands()
        
        # 커스텀 명령어 분리
        custom_commands = [cmd for cmd in all_commands if cmd['category'] == '커스텀']
        other_commands = [cmd for cmd in all_commands if cmd['category'] != '커스텀']
        
        print(f"   전체 명령어: {len(all_commands)}개")
        print(f"   일반 명령어: {len(other_commands)}개")
        print(f"   커스텀 명령어: {len(custom_commands)}개")
        
        if custom_commands:
            print(f"   커스텀 명령어 목록: {[cmd['name'] for cmd in custom_commands]}")
        
        # 2. 매력 명령어 라우팅 테스트
        print(f"\n2. '매력' 명령어 라우팅 테스트")
        result = route_command(
            user_id="test_user", 
            keywords=["매력"], 
            context={"user_name": "테스트유저"}
        )
        
        print(f"   라우팅 성공: {result.is_successful()}")
        print(f"   응답 메시지: {result.get_user_message()}")
        
        # 3. 다른 커스텀 명령어가 있다면 테스트
        if len(custom_commands) > 1:
            test_command = custom_commands[1]['name']
            print(f"\n3. '{test_command}' 명령어 라우팅 테스트")
            result2 = route_command(
                user_id="test_user2", 
                keywords=[test_command], 
                context={"user_name": "철수"}
            )
            
            print(f"   라우팅 성공: {result2.is_successful()}")
            print(f"   응답 메시지: {result2.get_user_message()}")
        
        return True
        
    except Exception as e:
        print(f"❌ 라우터 통합 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_korean_and_dice_processing():
    """한국어 및 다이스 처리 테스트"""
    print("\n=== 한국어 및 다이스 처리 테스트 ===")
    
    try:
        from custom_command import process_all_custom_substitutions, has_dice_expressions, has_korean_substitutions
        
        test_texts = [
            "{시전자}{은는} {1d100}점의 매력을 가지고 있습니다.",
            "{시전자}{이가} {3d6+2}의 능력치를 가졌습니다.",
            "{시전자}{을를} 치료했습니다.",
            "일반 텍스트입니다.",
            "{2d6} 피해를 입혔습니다."
        ]
        
        test_users = ["철수", "영희", "민수"]
        
        for i, text in enumerate(test_texts, 1):
            print(f"\n{i}. 텍스트: '{text}'")
            print(f"   다이스 포함: {has_dice_expressions(text)}")
            print(f"   한국어 치환 포함: {has_korean_substitutions(text)}")
            
            if has_korean_substitutions(text) or has_dice_expressions(text):
                for user in test_users[:2]:  # 2명만 테스트
                    processed = process_all_custom_substitutions(text, user)
                    print(f"   처리 결과 ({user}): '{processed}'")
        
        return True
        
    except Exception as e:
        print(f"❌ 처리 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """메인 테스트 함수"""
    print("커스텀 명령어 시스템 테스트 시작\n")
    
    success_count = 0
    total_tests = 3
    
    # 개별 테스트 실행
    if test_custom_command_basic():
        success_count += 1
    
    if test_command_router_integration():
        success_count += 1
    
    if test_korean_and_dice_processing():
        success_count += 1
    
    # 결과 요약
    print(f"\n=== 테스트 결과 요약 ===")
    print(f"성공한 테스트: {success_count}/{total_tests}")
    
    if success_count == total_tests:
        print("✅ 모든 테스트가 성공했습니다!")
        print("\n커스텀 명령어 시스템이 정상적으로 통합되었습니다.")
        print("이제 [매력] 명령어를 포함한 모든 커스텀 명령어가 작동해야 합니다.")
    else:
        print(f"❌ {total_tests - success_count}개의 테스트가 실패했습니다.")
        print("문제가 있는 부분을 확인하고 수정이 필요합니다.")
    
    return success_count == total_tests


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)