# Handoff — Winnow

Son güncelleme: 2026-09-10, güncelleyen: Claude Opus 5

## Şu an ne yapılıyor

Backtest deposu kararı **kapatıldı: mobx** (`packages/mobx`). Karar tahminle
değil ölçümle verildi; toplayıcı mobx üzerinde uçtan uca koştu ve 3 commit
sorunsuz toplandı.

**Seçim birimi kararı da kapatıldı (2026-09-10): birim artık test dosyası.**
Tasarım [`docs/superpowers/specs/2026-09-10-selection-unit-design.md`](docs/superpowers/specs/2026-09-10-selection-unit-design.md)
içinde; kod da yazıldı ve `feat/selection-unit` dalında birleştirildi (şema +
toplayıcı + seçim zinciri + `tools/collect_history.py` /
`tools/analyze_history.py` uyarlaması). Suite 82 test, hepsi yeşil. **Hâlâ
yapılmadı:** 3 mobx commit'inin yeni şemayla yeniden toplanıp ~0,9 MB/commit
tahmininin gerçek veriyle doğrulanması — bkz. "Sıradaki somut adımlar".

## Backtest deposu: neden mobx

Aday taraması (7 depo: rxjs, date-fns, immer, fp-ts, luxon, ts-morph, mobx)
beklenmedik bir yapısal gerçek çıkardı: **7 depodan sadece 2'si hâlâ Jest
kullanıyor.** rxjs, date-fns, immer ve fp-ts Vitest'e geçmiş. Toplayıcı
Jest/JUnit/Cobertura'ya bağlı olduğu için aday havuzu bu bulguyla daraldı.

rxjs ilk tercihti (246 kaynak dosya, en gerçekçi CI maliyeti) ama depo
açılınca elendi: **pnpm 10 + nx monorepo** (`npm ci` çalışmaz), üç ayrı Vitest
yapılandırması ve `RXJS_NEXT_TEST_MODE` anahtarı, ve depo şu anda yeniden
yazılıyor — geçmişe gidildiğinde test kurulumu tamamen değişiyor. Bu sonuncusu
ts-pattern'deki babel/v8 heap hatasının aynı ailesi: HEAD'de görünmez.

Diğer Vitest adayları da farklı sebeplerle elendi: zod (`nub` adlı özel paket
yöneticisi), date-fns (1539 kaynak dosyaya karşı ~5 test dosyası), fp-ts
(dtslint bağımlı), immer (ts-pattern'den küçük).

mobx mekanik olarak sıkıcı, ki aranan buydu: standart npm workspaces, düz
Jest, 56 kaynak dosyası, 32 test dosyası, harici servis yok.

## Ölçülen maliyet (mobx, gerçek koşu)

| | |
|---|---|
| `npm ci` (commit başına sabit) | 89 sn |
| `jest --listTests` | 16 sn |
| Test dosyası başına (sıcak önbellek) | ort. 17,4 sn (10–21) |
| Test dosyası başına (soğuk) | 43 sn |
| **Commit başına (3 commit'lik gerçek koşu)** | **674 sn ≈ 11,2 dk** |
| Kararlı hız (klon/ilk kurulum hariç) | 8,8 dk |
| Atlanan commit / dosya | 0 / 0 |
| Veritabanı büyüklüğü | 22,8 MB / commit |

30 commit ≈ **4,5–5,5 saat**, ~685 MB. Bir gecelik iş.

Not: dosya başına maliyet, dosyadaki test sayısından bağımsız. `api.js`
(2 test) ve `observables.js` (88 test) ikisi de ~17–19 sn. Bu, 2. bulgunun
(maliyet birimi test değil dosya) bağımsız doğrulaması.

## Yeni bulgu 1: mobx'te dosya seviyeli seçim ölü, satır seviyeli çalışıyor

11 test dosyası örneklendi ve coverage kesişimleri ölçüldü:

- **Dosya seviyesi:** 54 kaynak dosyanın **hepsi**, 11 testin **hepsi**
  tarafından kapsanıyor (K=11, istisnasız). Sebep barrel import — her test
  paketin giriş noktasını çekiyor. Dosya granülerliğinde aptal sezgisel her
  değişiklikte **tüm suite'i** seçer; yenilecek bir rakip yok.
- **Satır seviyesi:** 6.818 farklı kapsanan satır. **%15,1'i tek bir test**
  tarafından, **%45,4'ü tüm testler** tarafından kapsanıyor. Çiftler arası
  Jaccard: ortalama 0,762 (min 0,532, maks 0,892).

**Sonuç:** Winnow'un karşılaştıracağı dürüst temel çizgi **satır seviyeli
coverage** olmalı. Dosya seviyeli sezgiseli yenmek hileli bir karşılaştırma
olur, çünkü o baştan kaybediyor. Bimodal dağılım iyi haber: depoda hem çok
seçici hem kaçınılmaz olarak geniş değişiklikler var, yani precision/recall
ölçümü anlamlı.

## Yeni bulgu 2: mobx de gerçek etiket üretmiyor

3 commit'te 2.324 test sonucu, 9 başarısızlık. Ama üç farklı test, **üç
commit'in de hepsinde** başarısız:

```
makeAutoObservable + production build #2751   FAIL FAIL FAIL
Default debug names - production              FAIL FAIL FAIL
User provided debug names are always respected FAIL FAIL FAIL
```

Üçü de production build gerektiriyor; mobx bunları ayrı bir jest
yapılandırmasıyla koşuyor, `--selectProjects mobx` yalnızca temel projeyi
alıyor. Yani bunlar commit'in kırdığı testler değil, **sürekli kırık**
testler — varyansları sıfır, eğitim etiketi olarak değersiz.

**Yani ts-pattern'deki "0 patlama" bulgusu ikinci bir depoda doğrulandı.**
Mutasyon tabanlı yer gerçeği artık iki bağımsız ölçüme dayanıyor.

**Türetilen veri hijyeni kuralı:** sürekli başarısız testler yer gerçeğinden
dışlanmalı. Dışlanmazsa model "bu test hep kırılır" diye öğrenir ve
precision/recall yapay olarak şişer.

## Toplayıcıda bulunup düzeltilen dört kusur (hepsi test-önce)

1. **`--listTests` başlık satırı.** `--selectProjects` ile Jest stdout'un ilk
   satırına `Running one project: mobx` yazıyor; `list_test_files` bunu test
   yolu olarak kaydediyordu. Filtre metin kara listesi değil, satırın şekli
   üzerine kuruldu (Jest yolları her zaman mutlak).
2. **Paket kapsamı.** mobx'in kök config'i beş paketi kapsıyor. `jest_project`
   parametresi eklendi (`--selectProjects`); tek paketli depolarda bayrak hiç
   eklenmiyor, çünkü orada Jest hata veriyor. CLI'ya `--project` geldi.
   `collect_history`'ye parametre eklenmedi — zaten var olan bağımlılık
   enjeksiyon dikişi `functools.partial` ile kullanıldı.
3. **Ters bölü yolları.** Windows'ta Cobertura `packages\mobx\src\...`
   yazıyor, git diff'i `/` kullanıyor. Eşleşme olmazdı, `is_known_file` False
   dönerdi, seçici her seferinde tüm suite'i isterdi — **hiçbir hata mesajı
   olmadan.** `CoberturaParser` artık normalize ediyor. Gerçek veride
   doğrulandı: 126.396 satırın **0'ında** ters bölü var.
4. **Kodlama.** Alt süreçler `text=True` ile ama `encoding` olmadan
   çağrılıyordu, yani sistem yerel kodlaması (bu makinede **cp1254**). Jest
   çıktısındaki çözülemeyen baytlar okuma thread'ini öldürüyor ve yakalanan
   çıktı sessizce kayboluyor. Gerçek koşuda **6 kez** oldu. `run_tests_for_file`
   şansa hayatta kaldı (başarıyı rapor dosyalarının varlığından ölçüyor), ama
   `list_test_files` stdout'u **ayrıştırıyor** — orada olsaydı commit sessizce
   "0 test dosyası" olarak kaydedilirdi. `runner.py` (3 çağrı) ve `repo.py`
   (git) artık `encoding="utf-8", errors="replace"` kullanıyor.

Test sayısı 58 → 69, hepsi yeşil (seçim birimi işiyle birlikte şu an 82, hepsi yeşil).

## Seçim birimi kararı (2026-09-10, kapatıldı)

**Karar: Winnow'un seçim birimi test dosyası.** Tam gerekçe ve şema
`docs/superpowers/specs/2026-09-10-selection-unit-design.md` içinde; burada
sadece karara götüren argüman:

- **İki ayrı eksen var, önceki notta birbirine karışmıştı.** *Kaynak tarafı*
  (diff'i dosyayla mı satırla mı eşle) 2026-09-08'de satır seviyesi olarak
  kapandı. *Test tarafı* (seçilen ve skorlanan şey case mi dosya mı) bu
  karardı. Bağımsızlar; seçilen bileşim **satır × dosya**.
- **Belirleyici olan maliyet birimi, disk değil.** `api.js` (2 test) ve
  `observables.js` (88 test) ikisi de ~17–19 sn — maliyet Jest'in dosya başına
  başlatması. 88 testin 3'ünü seçmek hiçbir şey kazandırmaz. **Maliyet
  biriminden ince bir seçim birimi, tanımı gereği tasarruf üretemez.** Per-case
  attribution bedava ve kusursuz olsaydı bile CI kazancı sıfır ölçülürdü.
- 26 kat şişkinliğin gitmesi bu kararın *sonucu*, gerekçesi değil. İleride
  "depolama optimizasyonu" diye okunmamalı.
- Reddedilenler: gerçek per-case attribution toplamak (~3,7 sa/commit, ~25 kat,
  ve `-t` modülün tamamını yüklediği için hâlâ kısmen sahte) ve kimliği koruyup
  sadece depolamayı normalize etmek (aynı yalan, daha büyük şema).
- `test_outcomes` case seviyesinde kalıyor (`case_id`), `test_file` sütunu
  ekleniyor; `failure_rate` dosyaya yuvarlanıyor. Sürekli kırık testlerin
  dışlanması **minimum gözlem sayısı** koşuluyla yapılacak — Phase 2'deki
  circuit breaker'ın aynı deseni.

**Durum: tasarım uygulandı, kod `feat/selection-unit` dalında birleştirildi.**
Şema + toplayıcı + seçim zinciri yazıldı, test-önce; final review kusur
dalgası da kapatıldı (şema-koruma kontrolleri, `relative_posix` hata yakalama,
`failure_rate` gözlem sayacı düzeltmesi). Suite 82 test, hepsi yeşil.
**Hâlâ yapılmadı:** 3 mobx commit'inin yeni şemayla yeniden toplanıp
~0,9 MB/commit tahmininin gerçek veriyle doğrulanması — bkz. madde 1.

## Sıradaki somut adımlar

1. **Gerçek veriyle doğrulama.** 3 mobx commit'i yeni şemayla yeniden
   toplanıp ~0,9 MB/commit tahmini gerçek veriyle doğrulanacak. Bu adım
   henüz **yapılmadı**.
   Riskli nokta: `simulate/generator.py` ve `test_bootstrap_validation.py` eski
   kimliği konuşuyor — mekanik olarak yeniden adlandırılırsa artık var olmayan
   bir dünyayı doğrulamaya devam ederler.
2. **Toplayıcıya geçmişte adım atma seçeneği.** Şu an yalnızca "son N commit"
   toplanabiliyor (`git log main -N --reverse`). Araç zincirinin geçmişte
   nerede kırıldığını ölçmek için (ör. HEAD, HEAD~50, HEAD~200) aralık/adım
   desteği gerekiyor. Bugünkü 3 commit'lik koşu kablolamayı doğruladı ama
   geçmişe kayma riskini **ölçmedi**.
3. **Mutasyon tabanlı yer gerçeği** (`winnow/backtest/` + Stryker,
   `killedBy`/`coveredBy`). Artık iki depodan gelen ölçümle zorunlu.
   **Tasarımda ele alınması gereken asıl soru:** mutantlar gerçek hatalara
   benziyor mu (coupling hypothesis)? Benzemiyorsa model *hata yakalamayı*
   değil *mutant öldürmeyi* öğrenir; precision/recall mükemmel görünürken
   üretimde regresyon kaçar.
4. ML risk skorlayıcı, sonra GitHub Action.

## Toplama komutu

```bash
python tools/collect_history.py 30 \
  --repo https://github.com/mobxjs/mobx.git \
  --project mobx
```

Veri `data/mobx/` altında (gitignore'da, `data/*/` deseniyle).
