---
layout: default
title: ホーム
lang: ja
---

# Earnings Swing Trading Strategy Backtest

EODHD APIを使用したリアルタイムデータによる、中小型株に特化した決算ベーススイングトレード戦略の包括的なバックテストシステムです。

## 🚀 クイックスタート

### 前提条件
- Python 3.11以上
- [EODHD API](https://eodhistoricaldata.com/) キー

### インストール

```bash
# リポジトリをクローン
git clone https://github.com/tradermonty/earnings-trade-backtest.git
cd earnings-trade-backtest

# 仮想環境を作成・有効化
python3.11 -m venv venv
source venv/bin/activate  # macOS/Linux
# または
venv\Scripts\activate     # Windows

# 依存関係をインストール
pip install -r requirements.txt
```

### 環境設定

`.env` ファイルを作成し、APIキーを設定：

```env
EODHD_API_KEY=your_api_key_here
```

### 基本実行

```bash
# デフォルト設定で実行（過去1ヶ月）
python main.py

# 特定の期間を指定
python main.py --start_date 2025-01-01 --end_date 2025-06-30

# ヘルプを表示
python main.py --help
```

## 📋 主要機能

### 1. エントリー条件
- **決算サプライズ**: アナリスト予想を5%以上上回る
- **ギャップアップ**: 決算後の価格上昇≥0%
- **時価総額**: 中小型株フォーカス（$300M-$10B）
- **出来高**: 平均日次出来高の2倍以上
- **価格フィルタ**: ≥$10（ペニーストック除外）

### 2. 出口条件
- **ストップロス**: 6%の損失で自動退場
- **トレーリングストップ**: 21日移動平均線を下回る場合
- **最大保有期間**: 90日での強制決済
- **部分利確**: 8%の利益で35%のポジション決済（1日目）

### 3. リスク管理
- **ポジションサイズ**: 資金の6%
- **同時保有**: 最大10ポジション
- **セクター分散**: セクター当たり最大30%
- **日次リスクリミット**: 損失が6%を超える場合は新規取引停止

## 🔧 詳細なパラメータ設定

コマンドライン引数の完全なリストについては、[パラメータガイド](parameters.html) をご覧ください。

## 📊 レポート機能

システムは以下の形式でレポートを生成します：
- **HTML形式**: 美しいビジュアルレポート
- **CSV形式**: データ分析用のエクスポート

詳細については、[レポートガイド](reports.html) をご覧ください。

## 🧪 テスト

```bash
# 全テストを実行
python -m pytest tests/

# 特定のテストを実行
python -m pytest tests/test_components.py
```

## 📚 その他のドキュメント

- [パラメータ詳細](parameters.html)
- [レポート形式](reports.html)  
- [API仕様](api.html)
- [FAQ](faq.html)

## 📚 詳細ドキュメント

- [📋 パラメータガイド](parameters.md) - 各パラメータの詳細設定
- [📊 レポート形式説明](reports.md) - 生成されるレポートの読み方
- [❓ よくある質問（FAQ）](faq.md) - トラブルシューティングとベストプラクティス

## 📞 サポート

- [GitHub Issues](https://github.com/tradermonty/earnings-trade-backtest/issues)
- [プルリクエスト](https://github.com/tradermonty/earnings-trade-backtest/pulls)

## 📄 ライセンス

このプロジェクトは[MIT License](https://github.com/tradermonty/earnings-trade-backtest/blob/main/LICENSE)の下で公開されています。 