# 동적 계정 시스템 및 대소문자 구분 없는 계정명 처리 마이그레이션 가이드

이 가이드는 하드코딩된 마스토돈 계정 시스템을 동적 시스템으로 변경하고, 대소문자 구분 없는 계정명 처리를 추가하는 방법을 설명합니다.

## 📋 변경 개요

### 기존 시스템의 문제점
- 계정명(`NOTICE`, `SUBWAY` 등)이 코드에 하드코딩됨
- 새로운 서버에서 사용하려면 코드 수정이 필요
- 대소문자를 정확히 맞춰야 함

### 새 시스템의 장점
- **환경 변수만으로 계정 설정 가능**
- **코드 수정 없이 다른 서버에서 사용 가능**
- **대소문자 구분 없는 계정명 처리**
- **하위 호환성 유지**

---

## 🔧 수정사항 상세

### 1. config/settings.py 수정

#### 1-1. 필요한 import 추가
```python
# 기존
from typing import Optional, Dict, Any

# 수정 후
from typing import Optional, Dict, Any, List
```

#### 1-2. 동적 계정 로딩 시스템 추가

**기존 하드코딩된 계정 설정 제거:**
```python
# 삭제할 코드
self.MASTODON_ACCOUNTS = {
    'NOTICE': {
        'access_token': self._get_env_str('NOTICE_ACCESS_TOKEN', required=True, ...)
    },
    'SUBWAY': {
        'access_token': self._get_env_str('SUBWAY_ACCESS_TOKEN', required=True, ...)
    },
    # ... 기타 하드코딩된 계정들
}
```

**동적 계정 시스템으로 교체:**
```python
# 추가할 코드 (_initialize_settings 메서드 내)
# 동적 마스토돈 계정 설정
self.MASTODON_ACCOUNTS = self._load_mastodon_accounts()

# 기본 계정 설정 (첫 번째 계정)
self.DEFAULT_ACCOUNT = self._get_default_account()
```

#### 1-3. 동적 계정 로딩 메서드들 추가

**Config 클래스에 다음 메서드들 추가:**

```python
def _load_mastodon_accounts(self) -> Dict[str, Dict[str, str]]:
    """
    환경 변수에서 마스토돈 계정들을 동적으로 로드
    
    MASTODON_ACCOUNTS 환경 변수에서 계정 이름들을 읽어오고,
    각 계정별로 ACCESS_TOKEN을 조회합니다.
    
    예시 설정:
    MASTODON_ACCOUNTS=notice,company,announcement
    NOTICE_ACCESS_TOKEN=abc123
    COMPANY_ACCESS_TOKEN=def456
    ANNOUNCEMENT_ACCESS_TOKEN=ghi789
    """
    # 계정 목록을 환경 변수에서 읽기
    accounts_str = self._get_env_str(
        'MASTODON_ACCOUNTS', 
        default='notice,subway,story,whisper,station,alexey',  # 기본값 (하위 호환성)
        description="마스토돈 계정 이름들 (콤마로 구분)"
    )
    
    # 계정 이름들을 파싱
    account_names = [name.strip().upper() for name in accounts_str.split(',') if name.strip()]
    
    if not account_names:
        raise ValueError("MASTODON_ACCOUNTS가 비어있거나 유효하지 않습니다.")
    
    # 각 계정별로 ACCESS_TOKEN 로드
    accounts = {}
    for account_name in account_names:
        token_key = f"{account_name}_ACCESS_TOKEN"
        access_token = self._get_env_str(
            token_key,
            required=True,
            description=f"{account_name} 계정 액세스 토큰"
        )
        
        accounts[account_name] = {
            'access_token': access_token
        }
    
    return accounts

def _get_default_account(self) -> str:
    """기본 계정 반환 (첫 번째 계정 또는 명시적 설정)"""
    # 명시적으로 설정된 기본 계정이 있는지 확인
    default_account = self._get_env_str(
        'DEFAULT_MASTODON_ACCOUNT',
        description="기본 마스토돈 계정 이름"
    )
    
    if default_account:
        default_account = default_account.upper()
        if default_account in self.MASTODON_ACCOUNTS:
            return default_account
        else:
            print(f"경고: 설정된 기본 계정 '{default_account}'이 존재하지 않습니다. 첫 번째 계정을 사용합니다.")
    
    # 첫 번째 계정을 기본값으로 사용
    if self.MASTODON_ACCOUNTS:
        return list(self.MASTODON_ACCOUNTS.keys())[0]
    
    raise ValueError("설정된 마스토돈 계정이 없습니다.")

def get_account_list(self) -> List[str]:
    """사용 가능한 계정 목록 반환"""
    return list(self.MASTODON_ACCOUNTS.keys())

def is_valid_account(self, account_name: str) -> bool:
    """계정 이름이 유효한지 확인 (대소문자 구분 안함)"""
    return account_name.upper() in self.MASTODON_ACCOUNTS

def get_normalized_account_name(self, account_name: str) -> Optional[str]:
    """
    계정 이름을 정규화하여 실제 사용되는 대문자 형태로 반환
    시트에서 'notice', 'Notice', 'NOTICE' 등으로 써도 'NOTICE'로 반환
    """
    normalized = account_name.upper()
    if normalized in self.MASTODON_ACCOUNTS:
        return normalized
    return None
```

#### 1-4. 유니코드 이모지 제거 (선택사항)

Windows에서 인코딩 문제를 방지하기 위해:
```python
# 수정 전
print(f"✅ 환경 변수 파일 로드: {env_path}")
print(f"⚠️ 알 수 없는 시간대...")

# 수정 후  
print(f"환경 변수 파일 로드: {env_path}")
print(f"경고: 알 수 없는 시간대...")
```

---

### 2. core/mastodon_client.py 수정

#### 2-1. 주석 및 기본값 업데이트

```python
# 수정 전
account_name: 계정 이름 (NOTICE, SUBWAY 등)
account_name: str = 'NOTICE'
"""일반 툿 포스팅 (시스템 알림용, 기본적으로 NOTICE 계정 사용)"""

# 수정 후
account_name: 계정 이름 (동적으로 설정된 계정)
account_name: Optional[str] = None
"""일반 툿 포스팅 (시스템 알림용, 기본적으로 DEFAULT_ACCOUNT 사용)"""
```

#### 2-2. 기본 계정 처리 로직 수정

**post_toot 메서드 수정:**
```python
# 기존 코드에 추가
def post_toot(self, content: str, visibility: str = 'direct', 
              validate_content: bool = False, account_name: Optional[str] = None) -> TootResult:
    # 기본 계정 사용
    if account_name is None:
        account_name = config.DEFAULT_ACCOUNT
        
    return self.post_scheduled_toot(
        content=content,
        account_name=account_name,
        visibility=visibility
    )
```

#### 2-3. 대소문자 구분 없는 계정명 처리 추가

**post_scheduled_toot 메서드 수정:**
```python
def post_scheduled_toot(self, content: str, account_name: str, 
                       scheduled_at: Optional[datetime] = None,
                       visibility: str = 'unlisted') -> TootResult:
    # 계정 이름 정규화
    normalized_account = config.get_normalized_account_name(account_name)
    if not normalized_account:
        error_msg = f"존재하지 않는 계정: {account_name}. 사용 가능한 계정: {list(self.clients.keys())}"
        logger.error(error_msg)
        return TootResult(
            success=False,
            account_name=account_name,
            error_message=error_msg
        )
    account_name = normalized_account
    
    # 기존 로직 계속...
```

**check_account_connection 메서드 수정:**
```python
def check_account_connection(self, account_name: str) -> bool:
    """특정 계정 연결 상태 확인 (대소문자 구분 안함)"""
    # 계정 이름 정규화
    normalized_account = config.get_normalized_account_name(account_name)
    if not normalized_account:
        logger.error(f"존재하지 않는 계정: {account_name}")
        return False
    
    return self.clients[normalized_account].check_connection()
```

**get_account_info 메서드 수정:**
```python
def get_account_info(self, account_name: str) -> Optional[Dict[str, Any]]:
    """특정 계정 정보 조회 (대소문자 구분 안함)"""
    # 계정 이름 정규화
    normalized_account = config.get_normalized_account_name(account_name)
    if not normalized_account:
        logger.error(f"존재하지 않는 계정: {account_name}")
        return None
    
    return self.clients[normalized_account].get_bot_info()
```

#### 2-4. 기타 하드코딩 제거

```python
# 수정 전
def get_bot_info(self) -> Optional[Dict[str, Any]]:
    """기본 계정(NOTICE) 정보 반환 (하위 호환성)"""
    return self.get_account_info('NOTICE')

def send_system_notification(message: str, visibility: str = 'direct') -> TootResult:
    """시스템 알림 전송 (NOTICE 계정 사용)"""
    # ... 
    account_name='NOTICE'

# 수정 후
def get_bot_info(self) -> Optional[Dict[str, Any]]:
    """기본 계정 정보 반환 (하위 호환성)"""
    return self.get_account_info(config.DEFAULT_ACCOUNT)

def send_system_notification(message: str, visibility: str = 'direct') -> TootResult:
    """시스템 알림 전송 (기본 계정 사용)"""
    # ...
    account_name=config.DEFAULT_ACCOUNT
```

---

### 3. core/sheets_client.py 수정

#### 3-1. TootData 클래스의 계정 정규화 수정

**기존:**
```python
self.account = account.strip().upper() if account else ""  # 대문자로 정규화
```

**수정 후:**
```python
# 계정 이름 정규화 (대소문자 구분 없음)
from config.settings import config
if account:
    normalized_account = config.get_normalized_account_name(account.strip())
    self.account = normalized_account if normalized_account else account.strip().upper()
else:
    self.account = ""
```

#### 3-2. 계정 유효성 검사 메서드 수정

**기존:**
```python
def is_account_valid(self) -> bool:
    """계정 이름이 유효한지 확인"""
    valid_accounts = ['NOTICE', 'SUBWAY', 'STORY', 'WHISPER', 'STATION', 'ALEXEY']
    return self.account in valid_accounts
```

**수정 후:**
```python
def is_account_valid(self) -> bool:
    """계정 이름이 유효한지 확인"""
    from config.settings import config
    return config.is_valid_account(self.account)
```

---

### 4. 환경 변수 파일 (.env/.env.example) 수정

#### 4-1. 기존 하드코딩된 설정 제거

**삭제할 내용:**
```env
# 기존 하드코딩된 설정들
NOTICE_CLIENT_ID=...
NOTICE_CLIENT_SECRET=...
NOTICE_ACCESS_TOKEN=...

SUBWAY_CLIENT_ID=...
SUBWAY_CLIENT_SECRET=...
SUBWAY_ACCESS_TOKEN=...

# ... 기타 모든 계정의 CLIENT_ID, CLIENT_SECRET
```

#### 4-2. 새로운 동적 설정 추가

**새로 추가할 내용:**
```env
# Mastodon API 설정 (동적 계정 시스템)
# 사용할 계정들을 콤마로 구분하여 나열 (대소문자 무관)
MASTODON_ACCOUNTS=notice,subway,story,whisper,station,alexey

# 각 계정별 액세스 토큰 설정 (계정명은 대문자로)
NOTICE_ACCESS_TOKEN=your_token_here
SUBWAY_ACCESS_TOKEN=your_token_here
STORY_ACCESS_TOKEN=your_token_here
WHISPER_ACCESS_TOKEN=your_token_here
STATION_ACCESS_TOKEN=your_token_here
ALEXEY_ACCESS_TOKEN=your_token_here

# 기본 계정 설정 (선택사항, 미설정시 첫 번째 계정 사용)
DEFAULT_MASTODON_ACCOUNT=notice

# =========================================================================
# 다른 서버에서 사용할 때의 예시:
# MASTODON_ACCOUNTS=tester,announce
# TESTER_ACCESS_TOKEN=your_tester_token_here
# ANNOUNCE_ACCESS_TOKEN=your_announce_token_here
# DEFAULT_MASTODON_ACCOUNT=tester
# =========================================================================
```

---

## 🚀 다른 봇에 적용하기

### 1. 단계별 적용 방법

#### Step 1: config/settings.py 수정
1. `from typing import Optional, Dict, Any, List` import 추가
2. 하드코딩된 `MASTODON_ACCOUNTS` 설정을 `self._load_mastodon_accounts()` 호출로 교체
3. `self.DEFAULT_ACCOUNT = self._get_default_account()` 추가
4. 위에서 제공한 5개 메서드 추가:
   - `_load_mastodon_accounts()`
   - `_get_default_account()`
   - `get_account_list()`
   - `is_valid_account()`
   - `get_normalized_account_name()`

#### Step 2: Mastodon 클라이언트 수정
1. 하드코딩된 계정명(`'NOTICE'` 등) 모두 찾기
2. 기본 계정 참조를 `config.DEFAULT_ACCOUNT`로 변경
3. 계정명을 매개변수로 받는 메서드들에 정규화 로직 추가
4. Optional 계정명 매개변수 처리 추가

#### Step 3: 시트 클라이언트 수정 (해당하는 경우)
1. TootData 생성자에서 계정명 정규화 로직 추가
2. 하드코딩된 유효 계정 목록을 동적 검증으로 변경

#### Step 4: 환경 변수 파일 수정
1. CLIENT_ID, CLIENT_SECRET 모두 제거
2. `MASTODON_ACCOUNTS` 환경 변수 추가
3. 각 계정별 `{ACCOUNT}_ACCESS_TOKEN` 설정
4. `DEFAULT_MASTODON_ACCOUNT` 설정 (선택사항)

### 2. 검증 방법

**테스트 코드 예시:**
```python
# config 테스트
from config.settings import config

# 계정 목록 확인
print("계정 목록:", config.get_account_list())
print("기본 계정:", config.DEFAULT_ACCOUNT)

# 대소문자 구분 없는 검증
print("notice 유효성:", config.is_valid_account('notice'))  # True
print("Notice 유효성:", config.is_valid_account('Notice'))  # True
print("NOTICE 유효성:", config.is_valid_account('NOTICE'))  # True

# 정규화
print("notice ->", config.get_normalized_account_name('notice'))  # NOTICE
print("invalid ->", config.get_normalized_account_name('invalid'))  # None
```

### 3. 하위 호환성 확인

- 기존 코드가 여전히 작동하는지 확인
- 기본 계정이 올바르게 설정되는지 확인
- 모든 API 호출이 정상적으로 동작하는지 확인

---

## 📝 사용 예시

### 기본 사용법 (기존과 동일)
```python
manager = MultiMastodonManager()
result = manager.post_toot("안녕하세요!")  # 기본 계정으로 포스팅
```

### 특정 계정으로 포스팅 (대소문자 무관)
```python
manager = MultiMastodonManager()

# 모두 동일하게 작동
result1 = manager.post_scheduled_toot("테스트", "notice")
result2 = manager.post_scheduled_toot("테스트", "Notice") 
result3 = manager.post_scheduled_toot("테스트", "NOTICE")
```

### 다른 서버에서 사용
**.env 파일만 수정:**
```env
MASTODON_ACCOUNTS=tester,announce
TESTER_ACCESS_TOKEN=your_token
ANNOUNCE_ACCESS_TOKEN=your_token
DEFAULT_MASTODON_ACCOUNT=tester
```

**코드는 수정 없이 그대로 사용 가능!**

---

## ⚠️ 주의사항

1. **환경 변수 이름 규칙**: `{계정명}_ACCESS_TOKEN` 형태로 설정
2. **계정명은 대문자로 저장**: 내부적으로 모든 계정명은 대문자로 정규화됨
3. **하위 호환성**: 기본값으로 기존 계정들이 설정되어 있어 점진적 마이그레이션 가능
4. **에러 처리**: 잘못된 계정명 사용 시 명확한 에러 메시지 제공

이 가이드를 따라하면 다른 봇에도 동일한 동적 계정 시스템을 적용할 수 있습니다! 🎉