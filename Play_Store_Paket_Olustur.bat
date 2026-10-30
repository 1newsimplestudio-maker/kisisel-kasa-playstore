@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Kisisel Kasa - Google Play Store Paketleyici (AAB / APK)

:: Ust klasordeki en guncel main.py dosyasini PlayStore klasorune otomatik kopyala
if exist "..\main.py" (
    copy /Y "..\main.py" "main.py" >nul
)

set "FLET_EXE=C:\Users\pc\AppData\Local\Python\pythoncore-3.14-64\Scripts\flet.exe"
if not exist "%FLET_EXE%" set "FLET_EXE=flet"
set "PATH=%PATH%;C:\src\flutter\bin"

:MENU
cls
echo ====================================================================
echo      KİŞİSEL KASA - GOOGLE PLAY STORE PAKET OLUŞTURUCU
echo      (Tüm dosyalar ve çıktılar bu 'PlayStore' klasöründe tutulur)
echo ====================================================================
echo.
echo  [1] İmza Anahtarı Oluştur (upload-keystore.jks) - (İlk kez yapılıyorsa)
echo  [2] Google Play Store Paketi Üret (.AAB - Android App Bundle)
echo  [3] Telefona Direkt Kurulum Paketi Üret (.APK)
echo  [4] Çıkış
echo.
echo ====================================================================
set /p secim="Seçiminiz (1-4): "

if "%secim%"=="1" goto KEYSTORE
if "%secim%"=="2" goto BUILD_AAB
if "%secim%"=="3" goto BUILD_APK
if "%secim%"=="4" exit
goto MENU

:KEYSTORE
cls
echo [1] Google Play Store yükleme anahtarı (upload-keystore.jks) oluşturuluyor...
echo.
if exist "upload-keystore.jks" (
    echo UYARI: upload-keystore.jks zaten bu klasörde mevcut!
    pause
    goto MENU
)
keytool -genkey -v -keystore upload-keystore.jks -keyalg RSA -keysize 2048 -validity 10000 -alias upload
echo.
echo Anahtar oluşturuldu: %cd%\upload-keystore.jks
pause
goto MENU

:BUILD_AAB
cls
echo [2] Google Play Store için .AAB (Android App Bundle) derleniyor...
echo (Not: Yerel derleme için bilgisayarınızda Android SDK kurulu olmalıdır.)
echo.
if exist "..\main.py" copy /Y "..\main.py" "main.py" >nul
if exist "upload-keystore.jks" (
    set /p kspass="Keystore şifrenizi girin: "
    "%FLET_EXE%" build aab -o "apk_ve_aab_ciktilari\aab" --android-signing-key-store "%cd%\upload-keystore.jks" --android-signing-key-store-password "%kspass%" --android-signing-key-password "%kspass%" --android-signing-key-alias upload
) else (
    "%FLET_EXE%" build aab -o "apk_ve_aab_ciktilari\aab"
)
echo.
echo İşlem tamamlandıysa paketiniz şu klasördedir:
echo %cd%\apk_ve_aab_ciktilari\aab
pause
goto MENU

:BUILD_APK
cls
echo [3] Telefon için .APK dosyası derleniyor...
echo.
if exist "..\main.py" copy /Y "..\main.py" "main.py" >nul
"%FLET_EXE%" build apk -o "apk_ve_aab_ciktilari\apk"
echo.
echo İşlem tamamlandıysa paketiniz şu klasördedir:
echo %cd%\apk_ve_aab_ciktilari\apk
pause
goto MENU
