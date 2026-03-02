# station_time.xlsx 作成

## 入力（docs/station 直下の4 CSV）

| ファイル | 列構成 |
|----------|--------|
| station_time_to_shimbashi_master (1).csv | 駅名, 新橋まで所要時間(分) |
| station_time_to_toranomon_master (1).csv | 駅名, 虎ノ門まで所要時間(分) |
| station_time_to_toranomon_hills_master (1).csv | 駅名, 虎ノ門ヒルズまで所要時間(分) |
| station_time_to_uchisaiwaicho_master (1).csv | 駅名, 内幸町まで所要時間(分) |

## 出力（station_time.xlsx）

- **駅名**: 4 CSV を駅名でマージ（outer join）した全駅
- **職場まで所要時間(分)**: 4ファイル中 **最小** の所要時間
- **始発駅スコア**: 通勤コンパスランクに基づき自動付与
- **近隣スコア**: 0 で初期化（手動入力用）

## 実行方法

```bash
python scripts/build_station_time_from_csv.py
```

オプション: 第1引数でCSVディレクトリ、第2引数で出力パスを指定可能。
