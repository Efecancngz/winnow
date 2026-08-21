# Handoff — Winnow

Son güncelleme: 2026-08-21 12:15, güncelleyen: Claude Haiku 4.5

## Şu an ne yapılıyor

Tarih toplayıcısı (dört takip alt sisteminin ilki: toplama → mutasyon-temelli yer gerçeği →
ML risk skorörü → GitHub Action) tam olarak implementasyon tamamlandı ve gerçek 
ts-pattern deposuyla doğrulandı. Depo klonlanır, commit geçmişi yürütülür, Jest dosya 
başına çalıştırılarak dosya-düzeyinde kapsam atribütesi sağlanır, var olan Cobertura/JUnit 
ayrıştırıcıları ve SQLite deposu üzerinden yutulur. 6 görevin tümü tamamlandı, 53 test 
geçiyor (yavaş entegrasyon testi `@pytest.mark.slow` ile işaretli, varsayılan suite'ten 
hariç).

## Sıradaki somut adım

Mutasyon-temelli yer gerçeği (`winnow/backtest/` + Stryker, `killedBy`/`coveredBy` mutasyon 
rapor alanlarını kullanan) tasarlanacak ve implementasyon yapılacak sonraki alt sistemdir. 
Gerçek tarih verisi incelenebilir duruma geldikten sonra (yavaş entegrasyon testini veya 
tam 30-commit toplama çalıştırarak) yeni bir tasarım/beyin fırtınası geçişi başlatılmalı, 
Stryker entegrasyonu planlanmalı ve `winnow/backtest/` modülü tasarlanmalı.

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

- 26010f3 feat: add history collection orchestration with skip-and-continue error handling
- 8e15cbf feat: add per-test-file Jest execution with coverage and JUnit output
- b7f680b feat: add npm install and Jest test-file discovery
