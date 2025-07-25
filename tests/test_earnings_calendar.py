#!/usr/bin/env python3
"""
earnings-calendar API テストスクリプト
"""

import os
import requests
from dotenv import load_dotenv
from datetime import datetime, timedelta

load_dotenv()

api_key = os.getenv('FMP_API_KEY')
print('=== earnings-calendar API 詳細テスト ===')

# 1. ドキュメントの例通りのフォーマットでテスト
print('\n1. ドキュメント例のフォーマット:')
url = f'https://financialmodelingprep.com/api/v3/earnings-calendar?from=2025-01-10&to=2025-04-10&apikey={api_key}'
response = requests.get(url, timeout=30)
print(f'   Status: {response.status_code}')
if response.status_code == 200:
    data = response.json()
    print(f'   Results: {len(data)} items')
    if data and len(data) > 0:
        print('   最初の3件:')
        for item in data[:3]:
            print(f'     {item.get("symbol")}: {item.get("date")} - EPS: {item.get("epsActual")} vs {item.get("epsEstimated")}')

# 2. 過去のデータ（2024年11月）
print('\n2. 過去データ (2024年11月):')
url = f'https://financialmodelingprep.com/api/v3/earnings-calendar?from=2024-11-01&to=2024-11-30&apikey={api_key}'
response = requests.get(url, timeout=30)
if response.status_code == 200:
    data = response.json()
    print(f'   Results: {len(data)} items')
    if data and len(data) > 0:
        print('   最初の3件:')
        for item in data[:3]:
            print(f'     {item.get("symbol")}: {item.get("date")} - EPS: {item.get("epsActual")} vs {item.get("epsEstimated")}')

# 3. より短い期間（1日）
print('\n3. 短期間テスト (2024-11-04のみ):')
url = f'https://financialmodelingprep.com/api/v3/earnings-calendar?from=2024-11-04&to=2024-11-04&apikey={api_key}'
response = requests.get(url, timeout=30)
if response.status_code == 200:
    data = response.json()
    print(f'   Results: {len(data)} items')
    if data and len(data) > 0:
        print('   データ構造確認:')
        print(f'   Keys: {list(data[0].keys())}')

# 4. エラーメッセージの確認
print('\n4. ステータス確認:')
if response.status_code != 200:
    print(f'   Error response: {response.text}')
elif len(data) == 0:
    print('   APIは正常だがデータが返されない')
    print('   考えられる原因:')
    print('   - APIキーの権限不足')
    print('   - データ更新のタイミング')
    print('   - サーバー側の一時的な問題')

# 5. URLを表示して手動確認
print('\n5. デバッグ用URL:')
print(f'   {url[:100]}...')
print('   このURLをブラウザで開いて確認することも可能です')