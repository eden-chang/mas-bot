"""
상점 명령어 구현
Google Sheets에서 아이템 목록을 가져와 상점을 표시하는 명령어 클래스입니다.
"""

import os
import sys
from typing import List, Tuple, Any, Optional, Dict

# 경로 설정 (VM 환경 대응)
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

try:
    from config.settings import config
    from utils.logging_config import logger
    from utils.error_handling import CommandError
    from utils.cache_manager import bot_cache
    from commands.base_command import BaseCommand, CommandContext, CommandResponse
except ImportError:
    # VM 환경에서 임포트 실패 시 폴백
    import logging
    logger = logging.getLogger('shop_command')
    
    # 기본 클래스들 정의
    class CommandError(Exception):
        pass
    
    class BaseCommand:
        pass


class StoreCommand(BaseCommand):
    """
    상점 명령어 클래스
    
    Google Sheets의 '상점' 시트에서 구매 가능한 아이템 목록을 가져와 표시합니다.
    
    지원하는 형식:
    - [상점] : 구매 가능한 아이템 목록 표시
    - [아이템 목록] : 구매 가능한 아이템 목록 표시
    """
    
    # 명령어 메타데이터
    command_name = "상점"
    command_description = "구매 가능한 아이템 목록을 확인합니다"
    command_category = "인벤토리"
    command_examples = ["[상점]", "[아이템 목록]"]
    requires_sheets = True
    
    def execute(self, context: CommandContext) -> CommandResponse:
        """상점 명령어 실행"""
        try:
            # 명령어 매칭 확인
            if not self._matches_command(context.keywords):
                return CommandResponse.create_error("잘못된 명령어입니다")
            
            # 아이템 목록 조회
            shop_items = self._get_shop_items()
            
            if not shop_items:
                return CommandResponse.create_error("현재 상점에 판매중인 아이템이 없습니다.")
            
            # 화폐 단위 조회
            currency_unit = self._get_currency_unit()
            
            # 결과 메시지 생성
            message = self._format_shop_message(shop_items, currency_unit)
            
            return CommandResponse.create_success(message)
            
        except Exception as e:
            return CommandResponse.create_error(
                "상점 조회 중 오류가 발생했습니다",
                error=e
            )
    
    def _get_shop_items(self) -> List[Dict[str, Any]]:
        """
        상점 아이템 목록 조회 (동적 키 검색 적용)
        
        Returns:
            List[Dict]: 아이템 정보 리스트 [{'name': str, 'price': int, 'description': str, 'currency_unit': str}]
        """
        # 아이템 데이터 로드
        item_data_list = self._load_item_data()
        
        if not item_data_list:
            logger.warning("아이템 데이터가 없습니다.")
            return []
        
        shop_items = []
        
        # 각 아이템 정보 처리
        for item_data in item_data_list:
            try:
                item_name = str(item_data.get('아이템명', '')).strip()
                description = str(item_data.get('설명', '')).strip()
                
                # 아이템 이름이 없으면 스킵
                if not item_name:
                    continue
                
                # 동적 키 검색: 가격 컬럼
                price_key = None
                currency_from_price = None
                
                for key in item_data.keys():
                    if '가격' in key:
                        price_key = key
                        # 가격 헤더에서 화폐 단위 추출
                        if '(' in key and ')' in key:
                            import re
                            match = re.search(r'가격\s*\(([^)]+)\)', key)
                            if match:
                                currency_from_price = match.group(1).strip()
                        break
                
                # 가격 파싱
                if price_key:
                    price_str = str(item_data.get(price_key, '0')).strip()
                    
                    # '구매 불가' 아이템은 제외
                    if price_str.lower() in ['구매 불가', '구매불가', '불가']:
                        logger.debug(f"구매 불가 아이템 제외: {item_name}")
                        continue
                        
                    try:
                        price = int(float(price_str))
                    except (ValueError, TypeError):
                        logger.warning(f"아이템 '{item_name}'의 가격 파싱 실패: {price_str}")
                        price = 0
                else:
                    logger.warning(f"아이템 '{item_name}'의 가격 컬럼을 찾을 수 없습니다.")
                    price = 0
                
                # 설명이 없으면 기본 설명
                if not description:
                    description = "설명이 없습니다."
                
                shop_items.append({
                    'name': item_name,
                    'price': price,
                    'description': description,
                    'currency_unit': currency_from_price  # 각 아이템의 화폐 단위
                })
                
            except Exception as e:
                logger.warning(f"아이템 데이터 처리 실패: {item_data} -> {e}")
                continue
        
        return shop_items
    
    def _load_item_data(self) -> List[Dict[str, str]]:
        """
        아이템 데이터 로드 (캐시 우선, 시트 후순위)
        
        Returns:
            List[Dict]: 아이템 데이터 리스트
        """
        # 캐시에서 먼저 조회
        cached_data = bot_cache.get_item_data()
        if cached_data:
            logger.debug("캐시에서 아이템 데이터 로드")
            return cached_data
        
        # 시트에서 로드
        try:
            if self.sheets_manager:
                # 직접 '상점' 워크시트에서 데이터 가져오기
                item_data = self.sheets_manager.get_worksheet_data('상점', use_cache=False)
                if item_data:
                    # 캐시에 저장 (5분)
                    bot_cache.cache_item_data(item_data, ttl=300)
                    logger.debug(f"'상점' 시트에서 아이템 데이터 로드: {len(item_data)}개")
                    return item_data
                else:
                    logger.warning("'상점' 시트에서 데이터를 가져올 수 없습니다")
        except Exception as e:
            logger.warning(f"시트에서 아이템 데이터 로드 실패: {e}")
        
        # 빈 리스트 반환
        logger.info("아이템 데이터 없음")
        return []
    
    def _get_currency_unit(self) -> str:
        """
        화폐 단위 조회 (.env 우선, 헤더에서 추출 후순위) - 캐시 지원
        
        Returns:
            str: 화폐 단위
        """
        # 캐시에서 먼저 조회
        cached_currency = bot_cache.get_currency_unit()
        if cached_currency:
            return cached_currency
        
        currency = None
        import re
        import os
        
        try:
            # 0순위: .env에서 화폐 단위 조회
            env_currency = os.getenv('CURRENCY')
            if env_currency:
                currency = env_currency.strip()
                logger.debug(f".env에서 화폐 단위 추출: {currency}")
            
            # 1순위: 아이템 데이터의 가격 헤더에서 추출
            if not currency:
                item_data_list = self._load_item_data()
                if item_data_list:
                    sample_item = item_data_list[0]
                    for key in sample_item.keys():
                        if '가격' in key and '(' in key and ')' in key:
                            # '가격(갈레온)' -> '갈레온' 추출
                            match = re.search(r'가격\s*\(([^)]+)\)', key)
                            if match:
                                currency = match.group(1).strip()
                                logger.debug(f"아이템 가격 헤더에서 화폐 단위 추출: {key} -> {currency}")
                                break
            
            # 2순위: 사용자 데이터의 소지금 헤더에서 추출
            if not currency:
                try:
                    if self.sheets_manager:
                        user_data_list = self.sheets_manager.get_user_data()
                        if user_data_list:
                            sample_user = user_data_list[0]
                            for key in sample_user.keys():
                                if '소지금' in key and '(' in key and ')' in key:
                                    # '소지금(갈레온)' -> '갈레온' 추출
                                    match = re.search(r'소지금\s*\(([^)]+)\)', key)
                                    if match:
                                        currency = match.group(1).strip()
                                        logger.debug(f"사용자 소지금 헤더에서 화폐 단위 추출: {key} -> {currency}")
                                        break
                except Exception as e:
                    logger.debug(f"사용자 데이터에서 화폐 단위 추출 실패: {e}")
            
            # 3순위: 시트에서 직접 조회 (기존 패턴 지원)
            if not currency:
                if self.sheets_manager:
                    currency_setting = self.sheets_manager.get_currency_setting()
                    if currency_setting:
                        # '재화(갈레온)' 패턴
                        match = re.search(r'재화\s*\(([^)]+)\)', currency_setting)
                        if match:
                            currency = match.group(1).strip()
                            logger.debug(f"시트 설정에서 화폐 단위 추출: {currency_setting} -> {currency}")
                        # '소지금(갈레온)' 패턴
                        elif '소지금' in currency_setting:
                            match = re.search(r'소지금\s*\(([^)]+)\)', currency_setting)
                            if match:
                                currency = match.group(1).strip()
                                logger.debug(f"시트 설정에서 화폐 단위 추출: {currency_setting} -> {currency}")
            
            # 화폐 단위를 찾았으면 캐시에 저장
            if currency:
                bot_cache.cache_currency_unit(currency, ttl=1800)  # 30분 캐시
                return currency
                
        except Exception as e:
            logger.warning(f"화폐 단위 조회 실패: {e}")
        
        # 기본값 반환
        default_currency = "갈레온"
        bot_cache.cache_currency_unit(default_currency, ttl=1800)
        return default_currency
    
    def _matches_command(self, keywords: List[str]) -> bool:
        """명령어 매칭 확인"""
        if not keywords:
            return False
        
        first_keyword = keywords[0].lower()
        valid_commands = ['상점', '아이템 목록', '아이템목록', '상점목록']
        
        return first_keyword in valid_commands
    
    def _format_shop_message(self, shop_items: List[Dict[str, Any]], currency_unit: str) -> str:
        """
        상점 메시지 포맷팅
        
        Args:
            shop_items: 아이템 목록
            currency_unit: 화폐 단위
            
        Returns:
            str: 포맷된 결과 메시지
        """
        if not shop_items:
            return "현재 상점에 판매중인 아이템이 없습니다."
        
        lines = ["구매할 수 있는 아이템\n"]
        
        for item in shop_items:
            name = item.get('name', '알 수 없는 아이템')
            price = item.get('price', 0)
            description = item.get('description', '설명이 없습니다')
            item_currency = item.get('currency_unit') or currency_unit
            
            lines.append(f"• {name} ({price:,}{item_currency})")
            lines.append(f"  {description}")
            lines.append("")
        
        return "\n".join(lines)
    
    def get_help_text(self) -> str:
        """도움말 텍스트 반환"""
        return (f"{self.command_description}\n"
                f"사용법: {', '.join(self.command_examples)}\n"
                f"• Google Sheets '상점' 시트에서 정보를 가져옵니다\n"
                f"• 아이템명, 가격, 설명을 표시합니다")
    
    def get_shop_statistics(self) -> Dict[str, Any]:
        """
        상점 시스템 통계 정보 반환
        
        Returns:
            Dict: 상점 시스템 통계
        """
        try:
            # 아이템 데이터 로드
            shop_items = self._get_shop_items()
            
            if not shop_items:
                return {
                    'total_items': 0,
                    'available_items': 0,
                    'total_value': 0,
                    'average_price': 0,
                    'price_range': {'min': 0, 'max': 0},
                    'currency_unit': self._get_currency_unit()
                }
            
            # 통계 계산
            prices = [item['price'] for item in shop_items if item['price'] > 0]
            total_items = len(shop_items)
            available_items = len([item for item in shop_items if item['price'] > 0])
            total_value = sum(prices) if prices else 0
            average_price = total_value / len(prices) if prices else 0
            min_price = min(prices) if prices else 0
            max_price = max(prices) if prices else 0
            
            # 가격대별 분포
            price_ranges = {
                'free': len([p for p in [item['price'] for item in shop_items] if p == 0]),
                'low': len([p for p in prices if 0 < p <= 5]),
                'medium': len([p for p in prices if 5 < p <= 20]),
                'high': len([p for p in prices if p > 20])
            }
            
            # 화폐 단위별 분석
            currency_units = {}
            for item in shop_items:
                unit = item.get('currency_unit') or self._get_currency_unit()
                currency_units[unit] = currency_units.get(unit, 0) + 1
            
            return {
                'total_items': total_items,
                'available_items': available_items,
                'free_items': price_ranges['free'],
                'total_value': total_value,
                'average_price': round(average_price, 2),
                'price_range': {'min': min_price, 'max': max_price},
                'price_distribution': price_ranges,
                'currency_units': currency_units,  # 화폐 단위별 아이템 수
                'primary_currency': self._get_currency_unit(),
                'cache_available': bot_cache.get_item_data() is not None
            }
            
        except Exception as e:
            logger.error(f"상점 통계 조회 실패: {e}")
            return {'error': str(e)}
    
    def validate_shop_data(self) -> Dict[str, Any]:
        """
        상점 데이터 유효성 검증 (동적 키 검색 적용)
        
        Returns:
            Dict: 검증 결과
        """
        results = {
            'valid': True,
            'errors': [],
            'warnings': [],
            'info': {}
        }
        
        try:
            # 시트에서 아이템 데이터 로드 시도
            if self.sheets_manager:
                try:
                    item_data_list = self.sheets_manager.get_item_data()
                    if not item_data_list:
                        results['errors'].append("시트에 아이템 데이터가 없습니다.")
                    else:
                        results['info']['total_items'] = len(item_data_list)
                        
                        # 필수 컬럼 확인
                        required_columns = ['아이템명', '설명']
                        missing_columns = []
                        
                        if item_data_list:
                            first_row = item_data_list[0]
                            for col in required_columns:
                                if col not in first_row:
                                    missing_columns.append(col)
                            
                            # 가격 컬럼 동적 검색
                            price_column_found = False
                            for key in first_row.keys():
                                if '가격' in key:
                                    price_column_found = True
                                    results['info']['price_column'] = key
                                    break
                            
                            if not price_column_found:
                                missing_columns.append("가격 (가격 포함 컬럼)")
                        
                        if missing_columns:
                            results['errors'].append(f"필수 컬럼 누락: {', '.join(missing_columns)}")
                        
                        # 데이터 유효성 확인
                        empty_names = 0
                        invalid_prices = 0
                        empty_descriptions = 0
                        duplicate_names = []
                        currency_units = set()
                        
                        seen_names = set()
                        for item_data in item_data_list:
                            # 아이템명 확인
                            item_name = str(item_data.get('아이템명', '')).strip()
                            if not item_name:
                                empty_names += 1
                            elif item_name in seen_names:
                                duplicate_names.append(item_name)
                            else:
                                seen_names.add(item_name)
                            
                            # 가격 확인 (동적 키 검색)
                            price_key = None
                            for key in item_data.keys():
                                if '가격' in key:
                                    price_key = key
                                    # 화폐 단위 수집
                                    if '(' in key and ')' in key:
                                        import re
                                        match = re.search(r'가격\s*\(([^)]+)\)', key)
                                        if match:
                                            currency_units.add(match.group(1).strip())
                                    break
                            
                            if price_key:
                                try:
                                    price_str = str(item_data.get(price_key, '0')).strip()
                                    price = int(float(price_str))
                                    if price < 0:
                                        invalid_prices += 1
                                except (ValueError, TypeError):
                                    invalid_prices += 1
                            else:
                                invalid_prices += 1
                            
                            # 설명 확인
                            description = str(item_data.get('설명', '')).strip()
                            if not description:
                                empty_descriptions += 1
                        
                        # 화폐 단위 정보 추가
                        results['info']['currency_units'] = list(currency_units)
                        results['info']['primary_currency'] = self._get_currency_unit()
                        
                        # 경고 메시지 추가
                        if empty_names > 0:
                            results['warnings'].append(f"아이템명이 비어있는 항목이 {empty_names}개 있습니다.")
                        
                        if invalid_prices > 0:
                            results['warnings'].append(f"가격이 잘못된 항목이 {invalid_prices}개 있습니다.")
                        
                        if empty_descriptions > 0:
                            results['warnings'].append(f"설명이 비어있는 항목이 {empty_descriptions}개 있습니다.")
                        
                        if duplicate_names:
                            results['warnings'].append(f"중복된 아이템명: {', '.join(duplicate_names[:5])}")
                        
                        if len(currency_units) > 1:
                            results['warnings'].append(f"여러 화폐 단위 사용: {', '.join(currency_units)}")
                
                except Exception as e:
                    results['errors'].append(f"시트 데이터 로드 실패: {str(e)}")
            else:
                results['errors'].append("시트 매니저가 없습니다.")
            
            # 캐시 상태 확인
            results['info']['cache_available'] = bot_cache.get_item_data() is not None
            
            # 오류가 있으면 유효하지 않음
            if results['errors']:
                results['valid'] = False
            
        except Exception as e:
            results['valid'] = False
            results['errors'].append(f"검증 중 오류: {str(e)}")
        
        return results


# 상점 관련 유틸리티 함수들
def is_store_command(keyword: str) -> bool:
    """
    키워드가 상점 명령어인지 확인
    
    Args:
        keyword: 확인할 키워드
        
    Returns:
        bool: 상점 명령어 여부
    """
    if not keyword:
        return False
    
    keyword = keyword.lower().strip()
    return keyword in ['상점', '아이템 목록', '아이템목록', '상점목록']


def format_item_display(item: Dict[str, Any], fallback_currency: str = "갈레온") -> str:
    """
    아이템 표시 형식 생성 (개별 화폐 단위 지원)
    
    Args:
        item: 아이템 정보 {'name': str, 'price': int, 'description': str, 'currency_unit': str}
        fallback_currency: 폴백 화폐 단위
        
    Returns:
        str: 포맷된 아이템 문자열
    """
    name = item.get('name', '알 수 없는 아이템')
    price = item.get('price', 0)
    description = item.get('description', '설명이 없습니다.')
    currency_unit = item.get('currency_unit') or fallback_currency
    
    return f"{name} ({price}{currency_unit}) : {description}"


def calculate_total_shop_value(items: List[Dict[str, Any]]) -> int:
    """
    상점 전체 아이템 가치 계산
    
    Args:
        items: 아이템 리스트
        
    Returns:
        int: 총 가치
    """
    return sum(item.get('price', 0) for item in items)


def group_items_by_currency(items: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """
    화폐 단위별로 아이템 그룹화
    
    Args:
        items: 아이템 리스트
        
    Returns:
        Dict: {화폐단위: [아이템들]} 형태
    """
    grouped = {}
    for item in items:
        currency = item.get('currency_unit', '갈레온')
        if currency not in grouped:
            grouped[currency] = []
        grouped[currency].append(item)
    return grouped


# 상점 명령어 인스턴스 생성 함수
def create_store_command(sheets_manager=None) -> StoreCommand:
    """
    상점 명령어 인스턴스 생성
    
    Args:
        sheets_manager: Google Sheets 관리자
        
    Returns:
        StoreCommand: 상점 명령어 인스턴스
    """
    return StoreCommand(sheets_manager)