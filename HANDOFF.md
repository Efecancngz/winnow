# Handoff — Winnow

Son güncelleme: 2026-09-04 17:00, güncelleyen: Claude Sonnet 5

## Şu an ne yapılıyor

Tarih toplayıcısı tamamlandı ve **gerçek veri ilk kez toplandı**. HANDOFF'un
önceki sürümü "gerçek tarih verisi incelenebilir duruma geldikten sonra yeni
bir tasarım geçişi başlatılmalı" diyordu; o toplama koşuldu ve tasarımı
doğrudan etkileyen üç bulgu çıkardı (aşağıda).

Toplama `tools/collect_history.py` ile ts-pattern'in son 30 commit'i üzerinde
koşturuldu. **Bu satır yazılırken koşu hâlâ devam ediyordu (~20/30).** Veri
`data/ts-pattern/winnow.db` içinde ve gitignore'da; kaldığı yerden değil,
baştan koşulur (commit'ler `--reverse`, yani en eskiden başlar).

## Toplama sırasında bulunan ve düzeltilen kusur

Toplayıcı gerçek geçmişi **işleyemiyordu**. HEAD'de 48/48 test dosyası
başarıyla toplanıyordu, ama 9 ay geriye gidince (2025-08-31) her dosya
çöküyordu: `FATAL ERROR: Ineffective mark-compacts near heap limit`, 4GB'ta.
Heap'i 8GB'a çıkarmak çöküşü 8.1GB'a taşıdı — eksiklik değil, sınırsız
büyüme. Kurulu araç zinciri package.json ile birebir aynıydı.

Sebep: Jest'in varsayılan `babel` coverage sağlayıcısı, tip-ağır bir projeyi
enstrümante ediyor. Aynı dosya coverage'sız 1.5sn, `--coverageProvider=v8`
ile 4.4sn sürüyor ve Cobertura çıktısında aynı 7 `src/` kaydını veriyor —
`CoberturaParser` değişiklik gerektirmeden okuyor. Düzeltme commit `11245e0`.

**Ders (genel):** bir geçmiş toplayıcısını HEAD'de doğrulamak, tam da yapmak
zorunda olmadığı tek durumu test etmektir.

## Gerçek veriden çıkan üç bulgu (20 commit itibarıyla)

### 1. Gerçek geçmiş eğitim etiketi üretmiyor

**8.945 (commit, test) çiftinde 0 test patlaması.** Sağlıklı bir depoda
main'e kırık commit girmiyor. Bu, mutasyon-temelli yer gerçeğini bir tercih
değil **zorunluluk** yapıyor — ve artık gerekçesi teoriden değil sayıdan
geliyor. (Facebook'un *Predictive Test Selection* makalesinin uğraştığı
etiket kıtlığı probleminin ta kendisi.)

### 2. JUnit süreleri yanlış maliyet modeli

JUnit tüm suite için commit başına **~0.38 saniye** rapor ediyor; gerçekte
ödenen **dakikalar**. Ölçülen oran commit 29fbd3aa'da 244sn / 0.213sn =
**1.146×** (bu sayı `npm install`'ı da içeriyor; kurulum düşülüp 48 dosyaya
bölününce dosya başına ~4sn'ye karşı test başına ~0.005sn, yani ~800×).

Maliyetin %99.9'undan fazlası test yürütmesi değil, **dosya başına Jest
başlatma + tip kontrolü**. Sonuçları:

- Seçicinin değeri **atlanan test dosyası** ile ölçülmeli, atlanan test ile değil.
- Kazanç JUnit sürelerinden hesaplanırsa ~1000 kat küçük, anlamsız bir sayı çıkar.
- ML'in **seçim birimi** muhtemelen tek test değil, test dosyası olmalı.

### 3. ts-pattern backtest deneği olarak muhtemelen yanlış seçim

`distinct_source_files = 8`. Sekiz kaynak dosyalık bir depoda "hangi dosya
değişti → hangi testler koşsun" eşlemesi neredeyse aşikâr; kapsama tabanlı
aptal sezgisel muhtemelen yenilemez. Roadmap'in bitiş kriteri tam olarak
"ML'in precision/recall'unu aptal sezgisele karşı savunabilmek" olduğuna
göre, bu depo o karşılaştırmaya yer bırakmıyor.

Handoff'un önceki sürümü zaten "backtesting için henüz bir açık kaynak repo
seçilmedi" diyordu. **Bu karar hâlâ açık ve artık bilgilendirilmiş durumda:**
daha çok kaynak dosyası ve daha gerçek bir CI maliyeti olan bir depo gerekli.

## Sıradaki somut adım

1. **Backtest deposu kararı** — ts-pattern'i tutmak (küçük ama tanıdık) mı,
   daha büyük bir TS/Jest projesine geçmek mi. Bulgu 3 bunu tetikliyor.
2. **Mutasyon-temelli yer gerçeği tasarımı** (`winnow/backtest/` + Stryker,
   `killedBy`/`coveredBy`). Bulgu 1 bunu zorunlu kılıyor.
   **Tasarımda ele alınması gereken asıl soru:** mutantlar gerçek hatalara
   benziyor mu (coupling hypothesis)? Benzemiyorsa model *hata yakalamayı*
   değil *mutant öldürmeyi* öğrenir ve precision/recall mükemmel görünürken
   üretimde regresyon kaçırır.
3. ML risk skorlayıcı, sonra GitHub Action.

## Bilinmesi gerekenler

- Deterministik "must-run" kümesi ML tarafından asla daraltılmaz — sadece
  zenginleştirilir. `selection/pipeline.py` yazılırken korunmalı. Bunun
  metrik sonucu: **kaçırılan patlayan test ile boşuna koşulan test aynı
  maliyette değil**, yani precision ve recall eşit ağırlıkta değerlendirilemez.
- Toplama maliyeti: commit başına 4-10 dakika. Bağımlılık yükselten commit'ler
  (dependabot) belirgin şekilde yavaş, çünkü süre `npm install`'ı da içeriyor.
  Koşu sırasında commit başına süre 250sn'den 622sn'ye çıktı; npm çalkantısı mı
  ortam yavaşlaması mı **ayrıştırılamadı** (toplayıcı kurulum ile test süresini
  ayrı ölçmüyor — istenirse enstrümante edilebilir).
- v8 coverage'ın satır çözünürlüğü babel'den daha kaba olabilir
  (`is-matching.ts` için 1-52 arası kesintisiz kapsanmış görünüyor). Dosya
  düzeyi atribüsyon için sorun değil; model satır düzeyi granülerlik
  kullanacaksa doğrulanmalı.

## İlgili dosyalar

- `tools/collect_history.py` — gerçek geçmiş toplama (yeniden koşulabilir)
- `tools/analyze_history.py` — toplanan verinin ne içerdiğini raporlar
- `docs/superpowers/specs/2026-08-21-winnow-design.md` — onaylanmış tasarım
- `docs/architecture.md` — modül yapısı ve pattern kararları
- `docs/analiz.md` — §0 planlama çıktısı

## Son 3 commit

- tools: reproducible history collection and analysis entry points
- 11245e0 fix(collect): use the v8 coverage provider so real history is collectable
- b30deaa chore(jest-reporters): add package-lock.json from real npm install
