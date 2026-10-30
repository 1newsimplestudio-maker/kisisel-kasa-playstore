# Kişisel Kasa - Google Play Store Yükleme Rehberi (.AAB ve .APK)

Uygulamanın kök dizinini temiz tutmak için tüm **Google Play Store (`.aab`)** ve **Android Kurulum (`.apk`)** yapılandırma dosyaları bu **`PlayStore`** klasörü içerisine toplanmıştır.

## `PlayStore` Klasörü İçeriği
- **[Play_Store_Paket_Olustur.bat](file:///c:/Users/pc/Desktop/YZ/kasa/PlayStore/Play_Store_Paket_Olustur.bat):** Çalıştırıldığında ana klasördeki en güncel `main.py` dosyasını otomatik olarak buraya kopyalar ve `.aab` / `.apk` paketlerini `PlayStore\apk_ve_aab_ciktilari\` klasörüne üretir.
- **[pyproject.toml](file:///c:/Users/pc/Desktop/YZ/kasa/PlayStore/pyproject.toml) & [requirements.txt](file:///c:/Users/pc/Desktop/YZ/kasa/PlayStore/requirements.txt):** Google Play Store paket kimliği (`com.kisiselkasa.kisisel_kasa`), sürüm (`1.0.0`) ve bağımlılık ayarları.
- **[assets/icon.png](file:///c:/Users/pc/Desktop/YZ/kasa/PlayStore/assets/icon.png) & [assets/splash.png](file:///c:/Users/pc/Desktop/YZ/kasa/PlayStore/assets/splash.png):** 512x512 uygulama ikonu ve açılış ekranı görseli.
- **[.github/workflows/google_play_build.yml](file:///c:/Users/pc/Desktop/YZ/kasa/PlayStore/.github/workflows/google_play_build.yml):** Bilgisayara Android Studio kurmadan GitHub Actions üzerinde bulutta otomatik `.aab` ve `.apk` üretme iş akışı.
- **`apk_ve_aab_ciktilari/`:** Üretilen `.apk` ve `.aab` dosyalarının kaydedileceği klasör.
