# Handoff — Winnow

Son güncelleme: 2026-08-21 12:15, güncelleyen: Claude Haiku 4.5

## Şu an ne yapılıyor

Winnow çekirdek motoru (ingest, store, deterministic selection pipeline, risk scoring,
synthetic bootstrap validation) tam olarak implementasyon tamamlandı ve doğrulandı.
Tüm 12 görevin test süitleri geçiyor. End-to-end bootstrap validation test
(`test_bootstrap_validation.py`), deterministic selector'ün sentetik ground truth'a
karşı %100 recall (tam geri çağırım) elde ettiğini kanıtlıyor — bu, tüm tasarımın
dayanağı olan "safety-net" garantisinin somut kanıtı.

## Sıradaki somut adım

Takip eden aşama ML tabanlı risk scorer'ı geliştirmek, gerçek bir açık kaynak deposuyla
backtesting yapmak ve GitHub Action'ı entegre etmektir. Bunun için önce backtesting'e
konu olacak hedef açık kaynak repo karar verilmeli (şu an hâlâ açık soru).
Yeni bir implementasyon planı yazılmalı ve bu hedef seçildikten sonra başlanmalı.

## Bilinmesi gerekenler

- Deterministik "must-run" kümesi ML tarafından asla daraltılmaz — sadece
  zenginleştirilir. Bu kural `selection/pipeline.py` yazılırken korunmalı.
- Backtesting için henüz bir açık kaynak repo seçilmedi — implementasyon
  planında karara bağlanacak.

## İlgili dosyalar

- `docs/superpowers/specs/2026-08-21-winnow-design.md` — onaylanmış tasarım
- `docs/architecture.md` — modül yapısı ve pattern kararları
- `docs/analiz.md` — §0 planlama çıktısı

## Son 3 commit

- 2ba92aa feat: add synthetic coverage matrix generator for bootstrap validation
- 03fcc0d feat: add selection pipeline combining deterministic and risk-based selection
- cabadec feat: add pluggable risk scorer with heuristic baseline
