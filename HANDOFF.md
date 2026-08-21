# Handoff — Winnow

Son güncelleme: 2026-08-21 10:55, güncelleyen: Claude Sonnet 5

## Şu an ne yapılıyor

Proje scaffold'u (§3) ve planlama dokümanları (§0) yeni tamamlandı; henüz hiç
implementasyon kodu yazılmadı.

## Sıradaki somut adım

`superpowers:writing-plans` skill'i ile implementasyon planı çıkarılacak;
plan `ingest/` katmanından (Cobertura/JUnit parser'ları) başlamalı, çünkü
`store/` ve `selection/` ona bağımlı.

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

- (henüz commit yok)
