# Analiz — Winnow

Standart §0 planlama çıktısı. Tam tasarım gerekçesi için:
[docs/superpowers/specs/2026-08-21-winnow-design.md](superpowers/specs/2026-08-21-winnow-design.md).

## 1. Problem tanımı

CI'da her PR'da tüm test suite'ini çalıştırmak, suite büyüdükçe geri bildirim
döngüsünü yavaşlatıyor; oysa çoğu değişiklik test suite'inin sadece küçük bir
kısmını ilgilendiriyor.

## 2. Gereksinimler

**Fonksiyonel**
- PR diff'i verildiğinde coverage haritasından etkilenen testleri çıkarmak.
- Churn, geçmiş hata oranı, co-change sıklığı gibi özelliklerden risk skoru üretmek.
- Deterministik "must-run" kümesi ile ML risk sıralamasını birleştirip nihai liste üretmek.
- Cobertura/JUnit XML raporlarını parse edip veri deposuna yazmak.
- Bilinen hata enjeksiyonlarıyla sentetik commit geçmişi üretmek (ground truth doğrulaması için).
- Açık kaynak bir reponun geçmiş PR'larını replay edip precision/recall/süre kazancı raporu üretmek.
- GitHub Action olarak PR'a yorum bırakmak.

**Fonksiyonel olmayan**
- Recall güvenliği: coverage verisi eksikse asla sessizce test atlanmaz, tam suite'e düşülür.
- Tek repo ölçeği (yüzlerce–birkaç bin test); dağıtık/çoklu-repo kapsam dışı.
- Seçim hesaplaması saniyeler içinde tamamlanmalı.
- Ücretli/kapalı kaynak servise bağımlılık yok.
- Dilden bağımsız çekirdek — Cobertura/JUnit XML üretebilen her toolchain kullanabilir.

**İş gereksinimleri**
- Var olma nedeni: öğrenme + portföy, öğrenci seviyesinde nadir görülen bir teknik.
- Hedef kitle: teknik mülakatlar, GitHub ziyaretçileri.
- Başarı kriteri: gerçek bir açık kaynak repo üzerinde ölçülebilir sonuç (örn. "%X daha az test, %Y recall") + çalışan GitHub Action demosu.

## 3. Teknoloji & değişken seçimi

Python 3.12, SQLite, GitPython, `coverage.py` + Cobertura XML, `junitparser`,
scikit-learn, GitHub Actions. Tam alternatif-karşılaştırma tablosu:
[docs/architecture.md#tech-stack-decision-log](architecture.md#tech-stack-decision-log).

Config değişkenleri: `WINNOW_DB_PATH`, `WINNOW_COVERAGE_FORMAT`,
`WINNOW_RISK_THRESHOLD`, `WINNOW_MODE` — bkz. `.env.example`.

## 4. Sıfırdan mı, açık kaynaktan mı?

Taranan alternatifler: Launchable (kapalı kaynak SaaS), `pytest-testmon`
(açık kaynak ama saf coverage-diff, ML katmanı yok, Python/pytest-özel),
Google TIA / Meta 2019 Predictive Test Selection (yayınlanmış metodoloji,
kod yok). Coverage + ML hibrit, dilden bağımsız hazır bir araç bulunamadı.

**İstisna gerekçesi (§0.4):** bilinçli öğrenme projesi — amaç literatürdeki
tekniği bağımsız uygulayarak anlamak. Çözülmüş alt-problemler (XML parsing,
git diff, ML modeli) yine de hazır kütüphanelerle çözülüyor; özgün kısım
sadece hibrit seçim algoritması ve orkestrasyon.

## 5. Diyagramlar

Birden fazla bileşen birbiriyle konuşuyor (ingest → store → selection →
action) → component + sequence diyagramı gerekli. Bkz.
[docs/architecture.md](architecture.md).

## 6. API kontratı

Build vs. buy: coverage/test raporu formatları (Cobertura, JUnit XML) hazır
endüstri standardı, sıfırdan icat edilmiyor. GitHub Action girdi/çıktı
sözleşmesi: [docs/api-spec.md](api-spec.md).

## 7. Mimari & pattern kararı

Monolith-first, katmanlı paket. Adapter (rapor parser'ları), Repository
(SQLite), Strategy (risk skorlama). Bağımlılık yönü: `action` → `selection`
→ `store` → `ingest`. Detay: [docs/architecture.md](architecture.md).
