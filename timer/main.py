import os
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from apscheduler.schedulers.background import BackgroundScheduler
import time
from typing import List, Dict, Any, Optional

# 환경 변수 또는 직접 설정
CREDENTIALS_PATH = os.getenv('GOOGLE_CREDENTIALS_PATH', './credentials.json')
BOT_SPREADSHEET_ID = os.getenv('BOT_SPREADSHEET_ID', '1AM5NF7wloj5XkP1KTXhsovquMgdkTq2GrfEkRia-zFY')
RESET_WORKSHEET = os.getenv('RESET_WORKSHEET', '관리')
BOT_WORKSHEET = os.getenv('BOT_WORKSHEET', '메인 시트')
RESET_COLUMN = os.getenv('RESET_COLUMN', '오늘의 관찰 여부')

class TimerBot:
    def __init__(self):
        self.client = None
        self.scheduler = None
        self.is_running_reset = False

    def initialize(self):
        try:
            scope = ['https://www.googleapis.com/auth/spreadsheets']
            creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_PATH, scope)
            self.client = gspread.authorize(creds)
            self.scheduler = BackgroundScheduler(timezone="Asia/Seoul")
            print("Bot initialized successfully")
        except Exception as e:
            print(f"Failed to initialize bot: {e}")
            raise e

    def get_worksheet(self, spreadsheet_id: str, worksheet_name: str):
        try:
            spreadsheet = self.client.open_by_key(spreadsheet_id)
            return spreadsheet.worksheet(worksheet_name)
        except gspread.WorksheetNotFound:
            print(f"Worksheet '{worksheet_name}' not found.")
            return None
        except Exception as e:
            print(f"Error accessing spreadsheet or worksheet: {e}")
            return None

    def get_sheet_data(self, worksheet_name: str) -> List[List[str]]:
        try:
            worksheet = self.get_worksheet(BOT_SPREADSHEET_ID, worksheet_name)
            if worksheet:
                return worksheet.get_all_values()
        except Exception as e:
            print(f"Error getting sheet data from '{worksheet_name}': {e}")
        return []

    def get_column_index(self, worksheet_name: str, column_name: str):
        try:
            worksheet = self.get_worksheet(BOT_SPREADSHEET_ID, worksheet_name)
            if not worksheet:
                raise Exception(f"Worksheet '{worksheet_name}' not found.")

            headers = worksheet.row_values(1)
            try:
                column_index = headers.index(column_name)
                return column_index
            except ValueError:
                raise ValueError(f"Column '{column_name}' not found.")
        except Exception as e:
            print(f"Error getting column index for '{column_name}': {e}")
            raise e

    def _execute_batch_update(self, worksheet_name: str, update_info: List[Dict[str, Any]]):
        try:
            worksheet = self.get_worksheet(BOT_SPREADSHEET_ID, worksheet_name)
            if not worksheet:
                raise Exception(f"Worksheet '{worksheet_name}' not found for update.")

            cells_to_update = []
            for info in update_info:
                cell = worksheet.cell(row=info['row'], col=info['col'])
                cell.value = info['value']
                cells_to_update.append(cell)
            
            if cells_to_update:
                worksheet.update_cells(cells_to_update)
            return True
        except Exception as e:
            print(f"Batch update error: {e}")
            return False

    def reset_column_values(self, retry_count: int = 0):
        if self.is_running_reset:
            print('Reset already in progress, skipping...')
            return

        self.is_running_reset = True
        max_retries = 3
        retry_delays = [60, 120, 180]

        try:
            print(f"Starting reset for column '{RESET_COLUMN}' in worksheet '{RESET_WORKSHEET}'...")

            column_index = self.get_column_index(RESET_WORKSHEET, RESET_COLUMN)
            sheet_data = self.get_sheet_data(RESET_WORKSHEET)

            if len(sheet_data) <= 1:
                print("No data rows to reset")
                self.is_running_reset = False
                return

            column_letter = gspread.utils.col_to_letter(column_index + 1)
            data_row_count = len(sheet_data) - 1

            update_info = [{
                'row': i + 2, # 헤더 제외하고 2행부터 시작
                'col': column_index + 1,
                'value': 0
            } for i in range(data_row_count)]

            self._execute_batch_update(RESET_WORKSHEET, update_info)
            
            print(f"Successfully reset {data_row_count} rows in '{RESET_COLUMN}' column")

        except Exception as e:
            print(f"Error resetting column (attempt {retry_count + 1}): {e}")
            if retry_count < max_retries and isinstance(e, gspread.exceptions.APIError) and '429' in str(e):
                delay = retry_delays[retry_count]
                print(f"Retrying in {delay} seconds...")
                time.sleep(delay)
                self.is_running_reset = False
                self.reset_column_values(retry_count + 1)
            else:
                print('Max retries reached or non-API-limit error occurred')
        finally:
            self.is_running_reset = False

    def start(self):
        # KST 기준 매일 0시 0분에 리셋 실행
        self.scheduler.add_job(self.reset_column_values, 'cron', hour=0, minute=0)
        
        self.scheduler.start()
        print('Timer bot started. Scheduled daily tasks at 00:00 KST and 00:02 KST.')

    def test_run(self):
        print('Running test...')
        self.reset_column_values()


def main():
    bot = TimerBot()
    try:
        bot.initialize()
        
        # 테스트 실행을 원하면 주석 해제
        # bot.test_run()
        
        bot.start()
        
        try:
            while True:
                time.sleep(2)
        except (KeyboardInterrupt, SystemExit):
            bot.scheduler.shutdown()
            print('Bot shutting down...')
    except Exception as e:
        print(f'Failed to start bot: {e}')
        os._exit(1)


if __name__ == "__main__":
    main()