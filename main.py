# -*- coding: utf-8 -*-
"""
Kişisel Kasa ve Bütçe Takip Uygulaması (Aylık Takip & Sabit Gider Destekli)
===========================================================================
Teknoloji : Python & Flet (Material Design 3)
Veritabanı: SQLite3 (Tamamen yerel / offline çalışır - kasa.db)
Özellikler:
  - Aylık Bazda Gelir ve Gider Takibi (Ay/Yıl seçici ile geçmiş ve gelecek ayları görüntüleme)
  - Her Ay Ödenen Sabit Giderler Modülü (Kira, Fatura, Aidat, Abonelik vb. tanımlama,
    her ay tek tıkla veya topluca o ayın giderlerine işleme)
  - Karanlık (Dark) ve Aydınlık (Light) tema geçiş desteği (Varsayılan: Dark)
  - Ana Sayfa (Dashboard): Seçili ayda elde kalan net para, aylık gelir/gider özeti,
    bekleyen sabit gider uyarısı, hızlı işlem butonları ve seçili ayın hareketleri.
  - Kredi ve Taksit Takip Modülü: İlerleme çubuklu şık kartlar, seçili aya taksit ödeme.
  - Birikim Kasası Modülü: Ana bütçeden kenara ayrılan birikimleri artırma/azaltma.
"""

import os
import sqlite3
from datetime import datetime, timedelta
import flet as ft


# =====================================================================
# FLET SÜRÜM UYUMLULUK KATMANI (Flet 1.x ve Flet 0.2x Uyumlu)
# =====================================================================
Colors = getattr(ft, "Colors", getattr(ft, "colors", None))
Icons = getattr(ft, "Icons", getattr(ft, "icons", None))
Padding = getattr(ft, "Padding", getattr(ft, "padding", None))
Border = getattr(ft, "Border", getattr(ft, "border", None))
Alignment = getattr(ft, "Alignment", getattr(ft, "alignment", None))
FontWeight = ft.FontWeight
MainAxisAlignment = ft.MainAxisAlignment
CrossAxisAlignment = ft.CrossAxisAlignment

ALIGN_CENTER = getattr(Alignment, "CENTER", getattr(Alignment, "center", None))
ALIGN_TOP_LEFT = getattr(Alignment, "TOP_LEFT", getattr(Alignment, "top_left", None))
ALIGN_BOTTOM_RIGHT = getattr(
    Alignment, "BOTTOM_RIGHT", getattr(Alignment, "bottom_right", None)
)
WHITE_70 = getattr(Colors, "WHITE_70", getattr(Colors, "WHITE70", "#B3FFFFFF"))
WHITE_24 = getattr(Colors, "WHITE_24", getattr(Colors, "WHITE24", "#3DFFFFFF"))
WHITE_12 = getattr(Colors, "WHITE_12", getattr(Colors, "WHITE12", "#1FFFFFFF"))

TURKISH_MONTHS = {
    1: "Ocak",
    2: "Şubat",
    3: "Mart",
    4: "Nisan",
    5: "Mayıs",
    6: "Haziran",
    7: "Temmuz",
    8: "Ağustos",
    9: "Eylül",
    10: "Ekim",
    11: "Kasım",
    12: "Aralık",
}


def format_period_label(period_str: str) -> str:
    """'YYYY-MM' formatındaki dönemi 'Ekim 2026' şeklinde Türkçe metne çevirir."""
    try:
        year_s, month_s = period_str.split("-")
        month_name = TURKISH_MONTHS.get(int(month_s), month_s)
        return f"{month_name} {year_s}"
    except Exception:
        return period_str


def shift_period(period_str: str, delta_months: int) -> str:
    """'YYYY-MM' dönemini belirtilen ay sayısı kadar ileri veya geri kaydırır."""
    year, month = map(int, period_str.split("-"))
    total_months = (year * 12 + (month - 1)) + delta_months
    new_year = total_months // 12
    new_month = (total_months % 12) + 1
    return f"{new_year:04d}-{new_month:02d}"


def make_button(
    text: str,
    on_click=None,
    icon=None,
    bgcolor=None,
    color=None,
    disabled: bool = False,
    expand: bool = False,
) -> ft.Control:
    """Flet 1.x (ft.Button) ve Flet 0.2x (ft.ElevatedButton) uyumlu buton oluşturucu."""
    if hasattr(ft, "Button"):
        return ft.Button(
            content=text,
            icon=icon,
            bgcolor=bgcolor,
            color=color,
            disabled=disabled,
            expand=expand,
            on_click=on_click,
        )
    return ft.ElevatedButton(
        text=text,
        icon=icon,
        bgcolor=bgcolor,
        color=color,
        disabled=disabled,
        expand=expand,
        on_click=on_click,
    )


def make_text_button(text: str, on_click=None) -> ft.Control:
    """Flet 1.x ve 0.2x uyumlu TextButton oluşturucu."""
    try:
        return ft.TextButton(content=text, on_click=on_click)
    except TypeError:
        return ft.TextButton(text=text, on_click=on_click)


def make_dropdown_option(label: str):
    """Flet 1.x ve 0.2x uyumlu Dropdown seçeneği oluşturucu."""
    if hasattr(ft, "DropdownOption"):
        return ft.DropdownOption(key=label, text=label)
    return ft.dropdown.Option(label)


def format_currency(amount: float) -> str:
    """Sayısal tutarı Türkçe para birimi formatında (₺12.345,67) döndürür."""
    sign = "-" if amount < 0 else ""
    abs_val = abs(amount)
    formatted = f"{abs_val:,.2f}"
    formatted = formatted.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{sign}₺{formatted}"


# =====================================================================
# 1. VERİTABANI KATMANI (SQLite3)
# =====================================================================
class DatabaseManager:
    """
    Yerel SQLite veritabanı işlemlerini yöneten sınıf.
    Tablolar:
      - transactions   : Aylık gelir, gider ve birikim hareketleri (period: YYYY-MM)
      - fixed_expenses : Her ay düzenli ödenen sabit gider şablonları
      - installments   : Kredi ve taksit kayıtları
    """

    def __init__(self, db_name: str = "kasa.db"):
        if db_name == ":memory:":
            self.db_path = ":memory:"
        else:
            # Android / iOS cihazlarda kalıcı uygulama veri klasörünü (FLET_APP_STORAGE_DATA) kullan,
            # masaüstünde ise proje klasörünü kullan.
            storage_dir = os.environ.get("FLET_APP_STORAGE_DATA")
            if not storage_dir:
                storage_dir = os.path.dirname(os.path.abspath(__file__))
            os.makedirs(storage_dir, exist_ok=True)
            self.db_path = os.path.join(storage_dir, db_name)
        self.init_db()

    def get_connection(self) -> sqlite3.Connection:
        """SQLite veritabanı bağlantısı oluşturur ve satırları sözlük gibi döndürür."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        """
        Uygulama ilk açıldığında tabloları oluşturur ve eski veritabanı varsa
        yeni sütunları (period, fixed_expense_id) otomatik ekler.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # 1. İşlemler (Gelir / Gider / Birikim) Tablosu
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    type TEXT NOT NULL CHECK(type IN ('gelir', 'gider', 'birikim')),
                    category TEXT NOT NULL,
                    amount REAL NOT NULL,
                    description TEXT,
                    date TEXT NOT NULL,
                    period TEXT NOT NULL DEFAULT '',
                    fixed_expense_id INTEGER DEFAULT NULL
                )
                """
            )

            # Eski kasa.db dosyalarında period veya fixed_expense_id sütunu yoksa ekle
            cursor.execute("PRAGMA table_info(transactions)")
            existing_cols = {row["name"] for row in cursor.fetchall()}
            current_period = datetime.now().strftime("%Y-%m")

            if "period" not in existing_cols:
                cursor.execute(
                    f"ALTER TABLE transactions ADD COLUMN period TEXT NOT NULL DEFAULT '{current_period}'"
                )
            if "fixed_expense_id" not in existing_cols:
                cursor.execute(
                    "ALTER TABLE transactions ADD COLUMN fixed_expense_id INTEGER DEFAULT NULL"
                )

            # Boş period kayıtlarını güncelle
            cursor.execute(
                "UPDATE transactions SET period = ? WHERE period IS NULL OR period = ''",
                (current_period,),
            )

            # 2. Her Ay Ödenen Sabit Giderler Tablosu
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS fixed_expenses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    category TEXT NOT NULL,
                    amount REAL NOT NULL,
                    payment_day INTEGER NOT NULL DEFAULT 1
                )
                """
            )

            # 3. Kredi ve Taksitler Tablosu
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS installments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    total_installments INTEGER NOT NULL,
                    paid_installments INTEGER NOT NULL DEFAULT 0,
                    monthly_amount REAL NOT NULL,
                    end_date TEXT NOT NULL
                )
                """
            )
            conn.commit()

    # ------------------- İŞLEM (TRANSACTION) METOTLARI -------------------

    def add_transaction(
        self,
        tx_type: str,
        category: str,
        amount: float,
        description: str,
        period: str = None,
        date_str: str = None,
        fixed_expense_id: int = None,
    ) -> int:
        """Belirtilen ay (period: YYYY-MM) için yeni bir gelir, gider veya birikim ekler."""
        if not period:
            period = datetime.now().strftime("%Y-%m")
        if not date_str:
            date_str = datetime.now().strftime("%d.%m.%Y %H:%M")

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO transactions (
                    type, category, amount, description, date, period, fixed_expense_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tx_type,
                    category,
                    float(amount),
                    description.strip(),
                    date_str,
                    period,
                    fixed_expense_id,
                ),
            )
            conn.commit()
            return cursor.lastrowid

    def delete_transaction(self, tx_id: int) -> None:
        """Belirtilen ID'ye sahip işlemi siler."""
        with self.get_connection() as conn:
            conn.execute("DELETE FROM transactions WHERE id = ?", (tx_id,))
            conn.commit()

    def get_transactions(
        self, period: str = None, tx_type: str = None, limit: int = 100
    ) -> list:
        """
        İşlemleri yeniden eskiye doğru listeler.
        - period verilirse sadece ilgili ayın ('YYYY-MM') kayıtlarını getirir.
        - tx_type verilirse sadece ilgili tipteki ('gelir', 'gider', 'birikim') kayıtları getirir.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM transactions WHERE 1=1"
            params = []

            if period:
                query += " AND period = ?"
                params.append(period)
            if tx_type:
                query += " AND type = ?"
                params.append(tx_type)

            query += " ORDER BY id DESC LIMIT ?"
            params.append(limit)

            cursor.execute(query, tuple(params))
            return [dict(row) for row in cursor.fetchall()]

    def get_budget_summary(self, period: str = None) -> dict:
        """
        Seçili ay (period) ve genel toplam için bütçe özetini hesaplar:
        - Aylık Gelir, Aylık Gider, Aylık Birikime Ayrılan, Aylık Net Kalan Para
        - Genel Cüzdan Net Para (Tüm zamanların kümülatif elde kalan net parası)
        - Toplam Birikim Kasası (Tüm zamanların birikim toplamı)
        - Seçili ayda henüz ödenmemiş sabit gider toplamı
        """
        if not period:
            period = datetime.now().strftime("%Y-%m")

        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Seçili Ayın Geliri
            cursor.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE type = 'gelir' AND period = ?",
                (period,),
            )
            monthly_income = float(cursor.fetchone()[0])

            # Seçili Ayın Gideri
            cursor.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE type = 'gider' AND period = ?",
                (period,),
            )
            monthly_expense = float(cursor.fetchone()[0])

            # Seçili Ayda Birikime Ayrılan Net Tutar
            cursor.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE type = 'birikim' AND period = ?",
                (period,),
            )
            monthly_savings = float(cursor.fetchone()[0])

            # Seçili Ay Elde Kalan Net Para
            monthly_net = monthly_income - monthly_expense - monthly_savings

            # Tüm Zamanların Genel Cüzdan ve Birikim Kasası Toplamı
            cursor.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE type = 'gelir'"
            )
            all_income = float(cursor.fetchone()[0])

            cursor.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE type = 'gider'"
            )
            all_expense = float(cursor.fetchone()[0])

            cursor.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE type = 'birikim'"
            )
            total_savings_vault = float(cursor.fetchone()[0])

            overall_net_wallet = all_income - all_expense - total_savings_vault

            # Seçili ayda henüz ödenmemiş sabit giderlerin toplamı
            cursor.execute(
                """
                SELECT COALESCE(SUM(amount), 0)
                FROM fixed_expenses
                WHERE id NOT IN (
                    SELECT fixed_expense_id FROM transactions
                    WHERE period = ? AND fixed_expense_id IS NOT NULL
                )
                """,
                (period,),
            )
            unpaid_fixed_total = float(cursor.fetchone()[0])

            return {
                "period": period,
                "income": monthly_income,
                "expense": monthly_expense,
                "monthly_savings": monthly_savings,
                "net_wallet": monthly_net,
                "overall_net_wallet": overall_net_wallet,
                "savings": total_savings_vault,
                "unpaid_fixed": unpaid_fixed_total,
                "net_after_fixed": monthly_net - unpaid_fixed_total,
            }

    # ------------------- SABİT GİDERLER (FIXED EXPENSES) METOTLARI -------------------

    def add_fixed_expense(
        self, title: str, category: str, amount: float, payment_day: int = 1
    ) -> int:
        """Her ay tekrarlanan yeni bir sabit gider kalemi ekler."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO fixed_expenses (title, category, amount, payment_day)
                VALUES (?, ?, ?, ?)
                """,
                (title.strip(), category, float(amount), int(payment_day)),
            )
            conn.commit()
            return cursor.lastrowid

    def get_fixed_expenses_with_status(self, period: str) -> list:
        """
        Tüm sabit giderleri listeler ve seçili ayda (period) ödenip ödenmediği
        bilgisini ('is_paid', 'paid_tx_id') birlikte döndürür.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT
                    f.*,
                    t.id AS paid_tx_id,
                    t.date AS paid_date
                FROM fixed_expenses f
                LEFT JOIN transactions t
                    ON t.fixed_expense_id = f.id AND t.period = ?
                ORDER BY f.payment_day ASC, f.id DESC
                """,
                (period,),
            )
            results = []
            for row in cursor.fetchall():
                item = dict(row)
                item["is_paid"] = item["paid_tx_id"] is not None
                results.append(item)
            return results

    def pay_fixed_expense(self, fixed_id: int, period: str) -> bool:
        """
        Belirtilen sabit gideri seçili ayın (period) giderlerine işler.
        Eğer o ay için zaten ödenmişse tekrar eklemez.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM fixed_expenses WHERE id = ?", (fixed_id,)
            )
            row = cursor.fetchone()
            if not row:
                return False
            fixed = dict(row)

            cursor.execute(
                """
                SELECT id FROM transactions
                WHERE fixed_expense_id = ? AND period = ?
                """,
                (fixed_id, period),
            )
            if cursor.fetchone():
                return False

            now_str = datetime.now().strftime("%d.%m.%Y %H:%M")
            desc = f"[Sabit Gider] {fixed['title']} ({format_period_label(period)})"
            cursor.execute(
                """
                INSERT INTO transactions (
                    type, category, amount, description, date, period, fixed_expense_id
                )
                VALUES ('gider', ?, ?, ?, ?, ?, ?)
                """,
                (
                    fixed["category"],
                    fixed["amount"],
                    desc,
                    now_str,
                    period,
                    fixed_id,
                ),
            )
            conn.commit()
            return True

    def pay_all_unpaid_fixed_expenses(self, period: str) -> int:
        """Seçili ayda henüz ödenmemiş tüm sabit giderleri tek seferde gider olarak işler."""
        items = self.get_fixed_expenses_with_status(period)
        count = 0
        for item in items:
            if not item["is_paid"]:
                if self.pay_fixed_expense(item["id"], period):
                    count += 1
        return count

    def delete_fixed_expense(self, fixed_id: int) -> None:
        """Sabit gider tanımını siler."""
        with self.get_connection() as conn:
            conn.execute("DELETE FROM fixed_expenses WHERE id = ?", (fixed_id,))
            conn.commit()

    # ------------------- TAKSİT (INSTALLMENT) METOTLARI -------------------

    def add_installment(
        self,
        title: str,
        total_installments: int,
        paid_installments: int,
        monthly_amount: float,
        end_date: str,
    ) -> int:
        """Yeni bir kredi veya taksit kaydı oluşturur."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO installments (
                    title, total_installments, paid_installments, monthly_amount, end_date
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    title.strip(),
                    int(total_installments),
                    int(paid_installments),
                    float(monthly_amount),
                    end_date.strip(),
                ),
            )
            conn.commit()
            return cursor.lastrowid

    def get_installments(self) -> list:
        """Tüm kredi ve taksitleri listeler."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM installments ORDER BY id DESC")
            return [dict(row) for row in cursor.fetchall()]

    def pay_installment_step(self, inst_id: int, period: str = None) -> bool:
        """
        Bir taksitin ödenen sayısını 1 artırır ve aynı zamanda
        seçili ayın bütçesinden düşmesi için 'gider' olarak transactions tablosuna işler.
        """
        if not period:
            period = datetime.now().strftime("%Y-%m")

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM installments WHERE id = ?", (inst_id,))
            row = cursor.fetchone()
            if not row:
                return False

            inst = dict(row)
            if inst["paid_installments"] >= inst["total_installments"]:
                return False

            new_paid = inst["paid_installments"] + 1
            cursor.execute(
                "UPDATE installments SET paid_installments = ? WHERE id = ?",
                (new_paid, inst_id),
            )

            now_str = datetime.now().strftime("%d.%m.%Y %H:%M")
            desc = f"{inst['title']} ({new_paid}/{inst['total_installments']}. Taksit - {format_period_label(period)})"
            cursor.execute(
                """
                INSERT INTO transactions (type, category, amount, description, date, period)
                VALUES ('gider', 'Kredi / Taksit', ?, ?, ?, ?)
                """,
                (inst["monthly_amount"], desc, now_str, period),
            )
            conn.commit()
            return True

    def delete_installment(self, inst_id: int) -> None:
        """Taksit kaydını siler."""
        with self.get_connection() as conn:
            conn.execute("DELETE FROM installments WHERE id = ?", (inst_id,))
            conn.commit()


# =====================================================================
# 2. ARAYÜZ VE UYGULAMA KATMANI (Flet)
# =====================================================================
class PersonalSafeApp:
    """Flet tabanlı mobil uyumlu Kişisel Kasa ve Aylık Bütçe Takip Uygulaması."""

    INCOME_CATEGORIES = [
        "Maaş",
        "Serbest Çalışma (Freelance)",
        "Prim / Ek Gelir",
        "Kira Geliri",
        "Yatırım Getirisi",
        "Diğer Gelir",
    ]

    EXPENSE_CATEGORIES = [
        "Kira & Aidat",
        "Fatura (Elektrik/Su/Doğalgaz)",
        "İnternet & Telefon",
        "Market & Gıda",
        "Ulaşım & Yakıt",
        "Yeme & İçme",
        "Kredi / Taksit",
        "Alışveriş & Giyim",
        "Sağlık & Eğitim",
        "Dijital Abonelik",
        "Diğer Gider",
    ]

    SAVINGS_CATEGORIES = [
        "Acil Durum Fonu",
        "Altın / Döviz Birikimi",
        "Yatırım Hesabı",
        "Tatil / Seyahat Kumbarası",
        "Ev / Araç Hedefi",
        "Genel Birikim Kasası",
    ]

    def __init__(self, page: ft.Page):
        self.page = page
        self.db = DatabaseManager()
        self.current_tab_index = 0
        self.selected_period = datetime.now().strftime("%Y-%m")
        self.setup_page()
        self.build_ui()
        self.refresh_all()

    def setup_page(self) -> None:
        """Sayfa, pencere boyutu ve varsayılan aydınlık tema ayarlarını yapılandırır."""
        self.page.title = "Kişisel Kasa & Aylık Bütçe Takip"
        self.page.theme_mode = ft.ThemeMode.LIGHT  # Varsayılan olarak aydınlık tema
        self.page.padding = 0
        self.page.spacing = 0

        try:
            self.page.window.width = 430
            self.page.window.height = 860
            self.page.window.min_width = 360
            self.page.window.min_height = 640
        except Exception:
            pass

        self.page.theme = ft.Theme(color_scheme_seed=Colors.TEAL)
        self.page.dark_theme = ft.Theme(color_scheme_seed=Colors.TEAL)

    # ------------------- TEMA RENK YARDIMCILARI -------------------

    @property
    def is_dark(self) -> bool:
        return self.page.theme_mode == ft.ThemeMode.DARK

    @property
    def bg_color(self) -> str:
        return "#0F172A" if self.is_dark else "#F1F5F9"

    @property
    def card_color(self) -> str:
        return "#1E293B" if self.is_dark else "#FFFFFF"

    @property
    def text_primary(self) -> str:
        return "#F8FAFC" if self.is_dark else "#0F172A"

    @property
    def text_secondary(self) -> str:
        return "#94A3B8" if self.is_dark else "#64748B"

    @property
    def border_color(self) -> str:
        return "#334155" if self.is_dark else "#E2E8F0"

    # ------------------- BİLDİRİM & DIALOG YARDIMCILARI -------------------

    def show_snackbar(self, message: str, color: str = Colors.TEAL_600) -> None:
        """Ekranın altında kullanıcıya bilgi mesajı gösterir."""
        snack = ft.SnackBar(
            content=ft.Text(message, color=Colors.WHITE, weight=FontWeight.W_500),
            bgcolor=color,
            duration=2500,
        )
        if hasattr(self.page, "show_dialog"):
            self.page.show_dialog(snack)
        elif hasattr(self.page, "open"):
            self.page.open(snack)
        else:
            self.page.snack_bar = snack
            snack.open = True
            self.page.update()

    def open_dialog(self, dialog: ft.AlertDialog) -> None:
        """Dialog penceresini tüm Flet sürümleriyle uyumlu şekilde açar."""
        if hasattr(self.page, "show_dialog"):
            self.page.show_dialog(dialog)
        elif hasattr(self.page, "open"):
            self.page.open(dialog)
        else:
            self.page.dialog = dialog
            dialog.open = True
            self.page.update()

    def close_dialog(self, dialog: ft.AlertDialog) -> None:
        """Açık olan Dialog penceresini kapatır."""
        if hasattr(self.page, "pop_dialog"):
            self.page.pop_dialog()
        elif hasattr(self.page, "close"):
            self.page.close(dialog)
        else:
            dialog.open = False
            self.page.update()

    # ------------------- TEMA VE DÖNEM (AY) GEÇİŞİ -------------------

    def toggle_theme(self, e=None) -> None:
        """Aydınlık (Light) ve Karanlık (Dark) tema arasında geçiş yapar."""
        if self.page.theme_mode == ft.ThemeMode.DARK:
            self.page.theme_mode = ft.ThemeMode.LIGHT
            self.theme_btn.icon = Icons.DARK_MODE_OUTLINED
            self.theme_btn.icon_color = Colors.TEAL_700
            self.theme_btn.tooltip = "Karanlık Temaya Geç"
        else:
            self.page.theme_mode = ft.ThemeMode.DARK
            self.theme_btn.icon = Icons.LIGHT_MODE_OUTLINED
            self.theme_btn.icon_color = Colors.AMBER_400
            self.theme_btn.tooltip = "Aydınlık Temaya Geç"

        self.refresh_all()

    def change_period(self, delta: int) -> None:
        """Aktif ayı 1 ay ileri veya geri alır."""
        self.selected_period = shift_period(self.selected_period, delta)
        self.refresh_all()

    def reset_to_current_month(self, e=None) -> None:
        """Aktif ayı bugünün ayına döndürür."""
        self.selected_period = datetime.now().strftime("%Y-%m")
        self.refresh_all()

    # ------------------- ANA İSKELET OLUŞTURMA -------------------

    def build_ui(self) -> None:
        """Üst bar, ay seçici, içerik alanı ve alt navigasyon çubuğunu oluşturur."""
        self.theme_btn = ft.IconButton(
            icon=Icons.DARK_MODE_OUTLINED,
            icon_color=Colors.TEAL_700,
            tooltip="Karanlık Temaya Geç",
            on_click=self.toggle_theme,
        )

        # Üst Başlık Çubuğu (Header)
        self.header_bar = ft.Container(
            padding=Padding.symmetric(horizontal=16, vertical=10),
            content=ft.Row(
                alignment=MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=CrossAxisAlignment.CENTER,
                controls=[
                    ft.Row(
                        spacing=10,
                        controls=[
                            ft.Container(
                                width=36,
                                height=36,
                                border_radius=10,
                                bgcolor=Colors.TEAL_600,
                                alignment=ALIGN_CENTER,
                                content=ft.Icon(
                                    Icons.ACCOUNT_BALANCE_WALLET_ROUNDED,
                                    color=Colors.WHITE,
                                    size=20,
                                ),
                            ),
                            ft.Column(
                                spacing=1,
                                controls=[
                                    ft.Text(
                                        "Kişisel Kasa",
                                        size=17,
                                        weight=FontWeight.BOLD,
                                    ),
                                    ft.Text(
                                        "Aylık Bütçe & Sabit Gider Takibi",
                                        size=11,
                                        color=Colors.GREY_400,
                                    ),
                                ],
                            ),
                        ],
                    ),
                    self.theme_btn,
                ],
            ),
        )

        # Ay / Dönem Seçici Çubuğu
        self.period_bar_container = ft.Container(
            padding=Padding.symmetric(horizontal=16, vertical=6),
        )

        # Dinamik değişen sayfa gövdesi
        self.body_container = ft.Container(
            expand=True,
            padding=Padding.symmetric(horizontal=16, vertical=4),
        )

        # Alt Sekme Çubuğu
        self.nav_bar_container = ft.Container(
            padding=Padding.symmetric(horizontal=12, vertical=8),
        )

        # Ana Sayfa Düzeni (Mobil ekran çentikleri ve durum çubuğu için SafeArea ile sarılı)
        self.main_layout = ft.Container(
            expand=True,
            content=ft.SafeArea(
                expand=True,
                content=ft.Column(
                    spacing=0,
                    expand=True,
                    controls=[
                        self.header_bar,
                        self.period_bar_container,
                        self.body_container,
                        self.nav_bar_container,
                    ],
                ),
            ),
        )

        self.page.add(self.main_layout)

    def build_period_selector_bar(self) -> ft.Control:
        """Kullanıcının ayları değiştirebildiği şık dönem seçici çubuk."""
        current_now = datetime.now().strftime("%Y-%m")
        is_current_month = self.selected_period == current_now

        return ft.Container(
            border_radius=14,
            padding=Padding.symmetric(horizontal=10, vertical=4),
            bgcolor=self.card_color,
            border=Border.all(1, self.border_color),
            content=ft.Row(
                alignment=MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=CrossAxisAlignment.CENTER,
                controls=[
                    ft.IconButton(
                        icon=Icons.CHEVRON_LEFT_ROUNDED,
                        icon_size=22,
                        tooltip="Önceki Ay",
                        on_click=lambda e: self.change_period(-1),
                    ),
                    ft.Row(
                        spacing=8,
                        vertical_alignment=CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Icon(
                                Icons.CALENDAR_MONTH_ROUNDED,
                                size=18,
                                color=Colors.TEAL_400,
                            ),
                            ft.Text(
                                format_period_label(self.selected_period),
                                size=15,
                                weight=FontWeight.BOLD,
                                color=self.text_primary,
                            ),
                            ft.Container(
                                visible=not is_current_month,
                                ink=True,
                                on_click=self.reset_to_current_month,
                                padding=Padding.symmetric(horizontal=7, vertical=2),
                                border_radius=8,
                                bgcolor=Colors.TEAL_700,
                                content=ft.Text(
                                    "Bu Ay",
                                    size=10,
                                    color=Colors.WHITE,
                                    weight=FontWeight.BOLD,
                                ),
                            ),
                        ],
                    ),
                    ft.IconButton(
                        icon=Icons.CHEVRON_RIGHT_ROUNDED,
                        icon_size=22,
                        tooltip="Sonraki Ay",
                        on_click=lambda e: self.change_period(1),
                    ),
                ],
            ),
        )

    def switch_tab(self, index: int) -> None:
        """Alt menüdeki sekmeler arasında geçiş yapar."""
        self.current_tab_index = index
        self.refresh_all()

    def build_bottom_nav(self) -> ft.Control:
        """Mobil uyumlu 4 sekmeli alt navigasyon çubuğu."""
        tabs = [
            (0, "Aylık Cüzdan", Icons.DASHBOARD_ROUNDED),
            (1, "Sabit Gider", Icons. EVENT_REPEAT_ROUNDED if hasattr(Icons, "EVENT_REPEAT_ROUNDED") else Icons.REPEAT_ROUNDED),
            (2, "Taksitler", Icons.CREDIT_SCORE_ROUNDED),
            (3, "Birikim", Icons.SAVINGS_ROUNDED),
        ]

        nav_items = []
        for idx, label, icon_name in tabs:
            is_selected = self.current_tab_index == idx
            active_color = Colors.TEAL_400 if self.is_dark else Colors.TEAL_700
            inactive_color = self.text_secondary

            nav_items.append(
                ft.Container(
                    expand=True,
                    ink=True,
                    border_radius=14,
                    padding=Padding.symmetric(vertical=8),
                    bgcolor=(
                        (Colors.TEAL_900 if self.is_dark else Colors.TEAL_50)
                        if is_selected
                        else Colors.TRANSPARENT
                    ),
                    on_click=lambda e, i=idx: self.switch_tab(i),
                    content=ft.Column(
                        spacing=3,
                        horizontal_alignment=CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Icon(
                                icon_name,
                                size=20,
                                color=active_color if is_selected else inactive_color,
                            ),
                            ft.Text(
                                label,
                                size=10,
                                weight=(
                                    FontWeight.BOLD
                                    if is_selected
                                    else FontWeight.NORMAL
                                ),
                                color=active_color if is_selected else inactive_color,
                            ),
                        ],
                    ),
                )
            )

        return ft.Container(
            bgcolor=self.card_color,
            border_radius=18,
            padding=Padding.all(6),
            border=Border.all(1, self.border_color),
            content=ft.Row(
                alignment=MainAxisAlignment.SPACE_AROUND,
                controls=nav_items,
            ),
        )

    # =====================================================================
    # 3. EKRAN 1: ANA SAYFA (AYLIK DASHBOARD)
    # =====================================================================
    def build_dashboard_view(self) -> ft.Control:
        """
        Ana Sayfa (Seçili Ay Bazlı Dashboard):
        - Seçili ayda elde kalan net para + Genel Cüzdan bakiyesi
        - Seçili ayın Gelir, Gider ve Birikim özetleri
        - Bekleyen ödenmemiş sabit gider varsa hızlı uyarı ve ödeme geçişi
        - Hızlı işlem butonları: Gelir Ekle, Harcama Ekle, Sabit Gider, Taksit Ekle
        - Seçili aya ait hareket listesi
        """
        summary = self.db.get_budget_summary(self.selected_period)
        net_wallet = summary["net_wallet"]
        unpaid_fixed = summary["unpaid_fixed"]
        period_label = format_period_label(self.selected_period)
        recent_txs = self.db.get_transactions(period=self.selected_period, limit=50)

        # 1. Cüzdanda / Elde Kalan Net Para Kartı (Aylık)
        hero_card = ft.Container(
            border_radius=22,
            padding=Padding.all(18),
            gradient=ft.LinearGradient(
                begin=ALIGN_TOP_LEFT,
                end=ALIGN_BOTTOM_RIGHT,
                colors=(
                    ["#0F766E", "#115E59", "#134E4A"]
                    if net_wallet >= 0
                    else ["#991B1B", "#7F1D1D", "#450A0A"]
                ),
            ),
            content=ft.Column(
                spacing=12,
                horizontal_alignment=CrossAxisAlignment.START,
                controls=[
                    ft.Row(
                        alignment=MainAxisAlignment.SPACE_BETWEEN,
                        controls=[
                            ft.Row(
                                spacing=6,
                                controls=[
                                    ft.Icon(
                                        Icons.ACCOUNT_BALANCE_WALLET_OUTLINED,
                                        color=WHITE_70,
                                        size=17,
                                    ),
                                    ft.Text(
                                        f"{period_label.upper()} NET KALAN PARA",
                                        size=11,
                                        weight=FontWeight.W_600,
                                        color=WHITE_70,
                                    ),
                                ],
                            ),
                            ft.Container(
                                padding=Padding.symmetric(horizontal=8, vertical=3),
                                border_radius=8,
                                bgcolor=WHITE_12,
                                content=ft.Text(
                                    f"Genel Kasa: {format_currency(summary['overall_net_wallet'])}",
                                    size=10,
                                    color=Colors.WHITE,
                                ),
                            ),
                        ],
                    ),
                    # Büyük Aylık Net Para Göstergesi
                    ft.Text(
                        format_currency(net_wallet),
                        size=32,
                        weight=FontWeight.BOLD,
                        color=Colors.WHITE,
                    ),
                    ft.Divider(height=1, color=WHITE_24),
                    # Aylık Gelir - Aylık Gider - Birikim Kasası Alt Özeti
                    ft.Row(
                        alignment=MainAxisAlignment.SPACE_BETWEEN,
                        controls=[
                            self._build_mini_stat(
                                "Aylık Gelir",
                                format_currency(summary["income"]),
                                Icons.ARROW_UPWARD_ROUNDED,
                                Colors.GREEN_300,
                            ),
                            self._build_mini_stat(
                                "Aylık Gider",
                                format_currency(summary["expense"]),
                                Icons.ARROW_DOWNWARD_ROUNDED,
                                Colors.RED_300,
                            ),
                            self._build_mini_stat(
                                "Birikim Kasası",
                                format_currency(summary["savings"]),
                                Icons.SAVINGS_OUTLINED,
                                Colors.AMBER_300,
                            ),
                        ],
                    ),
                ],
            ),
        )

        # Bekleyen Sabit Gider Bilgi Çubuğu (Eğer bu ay ödenmemiş sabit gider varsa gösterilir)
        unpaid_fixed_banner = ft.Container(
            visible=unpaid_fixed > 0,
            border_radius=14,
            padding=Padding.symmetric(horizontal=14, vertical=10),
            bgcolor="#3B2F1E" if self.is_dark else "#FEF3C7",
            border=Border.all(1, Colors.AMBER_600),
            on_click=lambda e: self.switch_tab(1),
            ink=True,
            content=ft.Row(
                alignment=MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=CrossAxisAlignment.CENTER,
                controls=[
                    ft.Row(
                        spacing=10,
                        expand=True,
                        controls=[
                            ft.Icon(
                                Icons.NOTIFICATION_IMPORTANT_ROUNDED,
                                color=Colors.AMBER_400 if self.is_dark else Colors.AMBER_800,
                                size=20,
                            ),
                            ft.Column(
                                spacing=1,
                                expand=True,
                                controls=[
                                    ft.Text(
                                        f"Bu Ay Ödenmemiş Sabit Gider: {format_currency(unpaid_fixed)}",
                                        size=12,
                                        weight=FontWeight.BOLD,
                                        color=self.text_primary,
                                    ),
                                    ft.Text(
                                        f"Sabit giderler sonrası tahmini kalan: {format_currency(summary['net_after_fixed'])}",
                                        size=11,
                                        color=self.text_secondary,
                                    ),
                                ],
                            ),
                        ],
                    ),
                    ft.Icon(
                        Icons.ARROW_FORWARD_IOS_ROUNDED,
                        size=14,
                        color=self.text_secondary,
                    ),
                ],
            ),
        )

        # 2. Hızlı İşlem Butonları
        quick_actions = ft.Row(
            spacing=8,
            controls=[
                self._build_quick_action_btn(
                    title="Gelir Ekle",
                    icon=Icons.ADD_CIRCLE_OUTLINE_ROUNDED,
                    color=Colors.GREEN_600,
                    on_click=lambda e: self.open_transaction_modal("gelir"),
                ),
                self._build_quick_action_btn(
                    title="Harcama Ekle",
                    icon=Icons.REMOVE_CIRCLE_OUTLINE_ROUNDED,
                    color=Colors.RED_600,
                    on_click=lambda e: self.open_transaction_modal("gider"),
                ),
                self._build_quick_action_btn(
                    title="Sabit Gider",
                    icon=Icons.REPEAT_ROUNDED,
                    color=Colors.ORANGE_600,
                    on_click=lambda e: self.open_fixed_expense_modal(),
                ),
                self._build_quick_action_btn(
                    title="Taksit Ekle",
                    icon=Icons.CREDIT_CARD_ROUNDED,
                    color=Colors.INDIGO_500,
                    on_click=lambda e: self.open_installment_modal(),
                ),
            ],
        )

        # 3. Seçili Ayın Hareketleri Listesi
        tx_cards = []
        if not recent_txs:
            tx_cards.append(
                ft.Container(
                    padding=Padding.all(24),
                    border_radius=16,
                    bgcolor=self.card_color,
                    border=Border.all(1, self.border_color),
                    alignment=ALIGN_CENTER,
                    content=ft.Column(
                        horizontal_alignment=CrossAxisAlignment.CENTER,
                        spacing=8,
                        controls=[
                            ft.Icon(
                                Icons.RECEIPT_LONG_OUTLINED,
                                size=38,
                                color=self.text_secondary,
                            ),
                            ft.Text(
                                f"{period_label} döneminde henüz işlem yok.",
                                size=13,
                                weight=FontWeight.W_500,
                                color=self.text_primary,
                            ),
                            ft.Text(
                                "Yukarıdaki butonlarla bu aya gelir, harcama veya sabit gider ekleyebilirsiniz.",
                                size=11,
                                color=self.text_secondary,
                                text_align=ft.TextAlign.CENTER,
                            ),
                        ],
                    ),
                )
            )
        else:
            for tx in recent_txs:
                tx_cards.append(self._build_transaction_tile(tx))

        return ft.ListView(
            expand=True,
            spacing=12,
            padding=Padding.only(bottom=12),
            controls=[
                hero_card,
                unpaid_fixed_banner,
                ft.Text(
                    "Hızlı İşlemler",
                    size=13,
                    weight=FontWeight.BOLD,
                    color=self.text_primary,
                ),
                quick_actions,
                ft.Row(
                    alignment=MainAxisAlignment.SPACE_BETWEEN,
                    vertical_alignment=CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Text(
                            f"{period_label} Hareketleri",
                            size=13,
                            weight=FontWeight.BOLD,
                            color=self.text_primary,
                        ),
                        ft.Text(
                            f"{len(recent_txs)} işlem",
                            size=11,
                            color=self.text_secondary,
                        ),
                    ],
                ),
                ft.Column(spacing=8, controls=tx_cards),
            ],
        )

    def _build_mini_stat(
        self, label: str, value: str, icon_name: str, icon_color: str
    ) -> ft.Control:
        """Ana bakiye kartı içindeki küçük özet göstergelerini oluşturur."""
        return ft.Column(
            spacing=2,
            controls=[
                ft.Row(
                    spacing=4,
                    controls=[
                        ft.Icon(icon_name, size=13, color=icon_color),
                        ft.Text(label, size=10, color=WHITE_70),
                    ],
                ),
                ft.Text(value, size=13, weight=FontWeight.BOLD, color=Colors.WHITE),
            ],
        )

    def _build_quick_action_btn(
        self, title: str, icon: str, color: str, on_click
    ) -> ft.Control:
        """Ana sayfadaki hızlı işlem butonlarını oluşturur."""
        return ft.Container(
            expand=True,
            ink=True,
            on_click=on_click,
            border_radius=14,
            padding=Padding.symmetric(vertical=12, horizontal=4),
            bgcolor=self.card_color,
            border=Border.all(1, self.border_color),
            content=ft.Column(
                spacing=5,
                horizontal_alignment=CrossAxisAlignment.CENTER,
                controls=[
                    ft.Container(
                        width=34,
                        height=34,
                        border_radius=10,
                        bgcolor=color,
                        alignment=ALIGN_CENTER,
                        content=ft.Icon(icon, color=Colors.WHITE, size=18),
                    ),
                    ft.Text(
                        title,
                        size=11,
                        weight=FontWeight.W_600,
                        color=self.text_primary,
                        text_align=ft.TextAlign.CENTER,
                    ),
                ],
            ),
        )

    def _build_transaction_tile(self, tx: dict) -> ft.Control:
        """Tek bir gelir, gider veya birikim satırını şık bir kart olarak döndürür."""
        tx_type = tx["type"]
        amount = float(tx["amount"])

        if tx_type == "gelir":
            icon_name = Icons.TRENDING_UP_ROUNDED
            badge_color = Colors.GREEN_600
            amount_color = Colors.GREEN_400 if self.is_dark else Colors.GREEN_700
            prefix = "+"
            type_label = "Gelir"
        elif tx_type == "gider":
            icon_name = Icons.TRENDING_DOWN_ROUNDED
            badge_color = Colors.RED_600
            amount_color = Colors.RED_400 if self.is_dark else Colors.RED_700
            prefix = "-"
            type_label = "Harcama"
        else:  # birikim
            icon_name = Icons.SAVINGS_ROUNDED
            badge_color = Colors.AMBER_700
            amount_color = Colors.AMBER_400 if self.is_dark else Colors.AMBER_800
            prefix = "+" if amount >= 0 else "-"
            type_label = "Birikim Kasası"

        description_text = tx["description"] if tx["description"] else type_label

        return ft.Container(
            border_radius=14,
            padding=Padding.symmetric(horizontal=14, vertical=10),
            bgcolor=self.card_color,
            border=Border.all(1, self.border_color),
            content=ft.Row(
                alignment=MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=CrossAxisAlignment.CENTER,
                controls=[
                    ft.Row(
                        spacing=12,
                        expand=True,
                        controls=[
                            ft.Container(
                                width=38,
                                height=38,
                                border_radius=10,
                                bgcolor=badge_color,
                                alignment=ALIGN_CENTER,
                                content=ft.Icon(
                                    icon_name, color=Colors.WHITE, size=18
                                ),
                            ),
                            ft.Column(
                                spacing=2,
                                expand=True,
                                controls=[
                                    ft.Text(
                                        tx["category"],
                                        size=13,
                                        weight=FontWeight.BOLD,
                                        color=self.text_primary,
                                    ),
                                    ft.Text(
                                        f"{description_text} • {tx['date']}",
                                        size=11,
                                        color=self.text_secondary,
                                        max_lines=1,
                                        overflow=ft.TextOverflow.ELLIPSIS,
                                    ),
                                ],
                            ),
                        ],
                    ),
                    ft.Row(
                        spacing=2,
                        vertical_alignment=CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Text(
                                f"{prefix}{format_currency(abs(amount))}",
                                size=13,
                                weight=FontWeight.BOLD,
                                color=amount_color,
                            ),
                            ft.IconButton(
                                icon=Icons.DELETE_OUTLINE_ROUNDED,
                                icon_size=18,
                                icon_color=self.text_secondary,
                                tooltip="İşlemi Sil",
                                on_click=lambda e, tid=tx["id"]: self.handle_delete_tx(
                                    tid
                                ),
                            ),
                        ],
                    ),
                ],
            ),
        )

    def handle_delete_tx(self, tx_id: int) -> None:
        """Bir işlemi siler ve ekranı günceller."""
        self.db.delete_transaction(tx_id)
        self.show_snackbar("Kayıt silindi.", Colors.BLUE_GREY_700)
        self.refresh_all()

    # =====================================================================
    # 4. EKRAN 2: HER AY ÖDENEN SABİT GİDERLER MODÜLÜ
    # =====================================================================
    def build_fixed_expenses_view(self) -> ft.Control:
        """
        Her Ay Ödenen Sabit Giderler Modülü:
        - Kira, aidat, elektrik/su/internet faturaları, abonelikler gibi her ay
          düzenli ödenen sabit giderleri listeler.
        - Seçili ayda (Örn: Ekim 2026) hangilerinin ödendiğini, hangilerinin beklediğini gösterir.
        - Tek tıkla veya topluca seçili ayın giderlerine işleme imkanı sunar.
        """
        period_label = format_period_label(self.selected_period)
        fixed_items = self.db.get_fixed_expenses_with_status(self.selected_period)

        total_fixed = sum(float(i["amount"]) for i in fixed_items)
        paid_fixed = sum(
            float(i["amount"]) for i in fixed_items if i["is_paid"]
        )
        unpaid_fixed = total_fixed - paid_fixed
        unpaid_count = sum(1 for i in fixed_items if not i["is_paid"])

        summary_card = ft.Container(
            border_radius=20,
            padding=Padding.all(18),
            gradient=ft.LinearGradient(
                begin=ALIGN_TOP_LEFT,
                end=ALIGN_BOTTOM_RIGHT,
                colors=["#C2410C", "#9A3412", "#7C2D12"],
            ),
            content=ft.Column(
                spacing=12,
                controls=[
                    ft.Row(
                        alignment=MainAxisAlignment.SPACE_BETWEEN,
                        controls=[
                            ft.Column(
                                spacing=2,
                                controls=[
                                    ft.Text(
                                        f"AYLIK SABİT GİDER TOPLAMI ({period_label.upper()})",
                                        size=10,
                                        color=WHITE_70,
                                        weight=FontWeight.W_600,
                                    ),
                                    ft.Text(
                                        format_currency(total_fixed),
                                        size=26,
                                        weight=FontWeight.BOLD,
                                        color=Colors.WHITE,
                                    ),
                                ],
                            ),
                            make_button(
                                text="+ Sabit Gider",
                                bgcolor=Colors.ORANGE_600,
                                color=Colors.WHITE,
                                on_click=lambda e: self.open_fixed_expense_modal(),
                            ),
                        ],
                    ),
                    ft.Divider(height=1, color=WHITE_24),
                    ft.Row(
                        alignment=MainAxisAlignment.SPACE_BETWEEN,
                        controls=[
                            ft.Text(
                                f"Ödenen: {format_currency(paid_fixed)}",
                                size=12,
                                color=Colors.GREEN_300,
                                weight=FontWeight.BOLD,
                            ),
                            ft.Text(
                                f"Bekleyen: {format_currency(unpaid_fixed)}",
                                size=12,
                                color=Colors.AMBER_200,
                                weight=FontWeight.BOLD,
                            ),
                        ],
                    ),
                    ft.Container(
                        visible=unpaid_count > 0,
                        padding=Padding.only(top=4),
                        content=make_button(
                            expand=True,
                            text=f"Tüm Bekleyen Sabit Giderleri {period_label} Ayına İşle ({unpaid_count})",
                            icon=Icons.DONE_ALL_ROUNDED,
                            bgcolor=Colors.TEAL_600,
                            color=Colors.WHITE,
                            on_click=lambda e: self.handle_pay_all_fixed(),
                        ),
                    ),
                ],
            ),
        )

        cards = []
        if not fixed_items:
            cards.append(
                ft.Container(
                    padding=Padding.all(26),
                    border_radius=16,
                    bgcolor=self.card_color,
                    border=Border.all(1, self.border_color),
                    alignment=ALIGN_CENTER,
                    content=ft.Column(
                        horizontal_alignment=CrossAxisAlignment.CENTER,
                        spacing=8,
                        controls=[
                            ft.Icon(
                                Icons.REPEAT_ROUNDED,
                                size=40,
                                color=self.text_secondary,
                            ),
                            ft.Text(
                                "Henüz sabit gider tanımlanmadı.",
                                size=14,
                                weight=FontWeight.W_500,
                                color=self.text_primary,
                            ),
                            ft.Text(
                                "Kira, aidat, elektrik, internet, abonelik gibi her ay düzenli ödediğiniz giderleri ekleyebilirsiniz.",
                                size=12,
                                color=self.text_secondary,
                                text_align=ft.TextAlign.CENTER,
                            ),
                        ],
                    ),
                )
            )
        else:
            for item in fixed_items:
                cards.append(self._build_fixed_expense_card(item, period_label))

        return ft.ListView(
            expand=True,
            spacing=12,
            padding=Padding.only(bottom=12),
            controls=[
                summary_card,
                ft.Text(
                    f"Her Ay Ödenen Sabit Giderler ({period_label} Durumu)",
                    size=13,
                    weight=FontWeight.BOLD,
                    color=self.text_primary,
                ),
                ft.Column(spacing=8, controls=cards),
            ],
        )

    def _build_fixed_expense_card(self, item: dict, period_label: str) -> ft.Control:
        """Tek bir sabit gider kartını seçili aydaki ödeme durumuyla birlikte oluşturur."""
        is_paid = item["is_paid"]
        amount = float(item["amount"])
        day = int(item["payment_day"])

        return ft.Container(
            border_radius=16,
            padding=Padding.all(14),
            bgcolor=self.card_color,
            border=Border.all(
                1, Colors.GREEN_700 if is_paid else self.border_color
            ),
            content=ft.Column(
                spacing=10,
                controls=[
                    ft.Row(
                        alignment=MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Row(
                                spacing=10,
                                expand=True,
                                controls=[
                                    ft.Container(
                                        width=38,
                                        height=38,
                                        border_radius=10,
                                        bgcolor=(
                                            Colors.GREEN_600
                                            if is_paid
                                            else Colors.ORANGE_600
                                        ),
                                        alignment=ALIGN_CENTER,
                                        content=ft.Icon(
                                            (
                                                Icons.CHECK_CIRCLE_ROUNDED
                                                if is_paid
                                                else Icons.EVENT_REPEAT_ROUNDED
                                                if hasattr(
                                                    Icons, "EVENT_REPEAT_ROUNDED"
                                                )
                                                else Icons.REPEAT_ROUNDED
                                            ),
                                            color=Colors.WHITE,
                                            size=20,
                                        ),
                                    ),
                                    ft.Column(
                                        spacing=2,
                                        expand=True,
                                        controls=[
                                            ft.Text(
                                                item["title"],
                                                size=14,
                                                weight=FontWeight.BOLD,
                                                color=self.text_primary,
                                            ),
                                            ft.Text(
                                                f"{item['category']} • Her ayın {day}. günü",
                                                size=11,
                                                color=self.text_secondary,
                                            ),
                                        ],
                                    ),
                                ],
                            ),
                            ft.Text(
                                format_currency(amount),
                                size=15,
                                weight=FontWeight.BOLD,
                                color=(
                                    (Colors.GREEN_400 if self.is_dark else Colors.GREEN_700)
                                    if is_paid
                                    else (Colors.ORANGE_400 if self.is_dark else Colors.ORANGE_700)
                                ),
                            ),
                        ],
                    ),
                    ft.Row(
                        alignment=MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Text(
                                (
                                    f"✓ {period_label} ayında ödendi"
                                    if is_paid
                                    else f"⏳ {period_label} ayı için ödeme bekliyor"
                                ),
                                size=11,
                                color=(
                                    (Colors.GREEN_400 if self.is_dark else Colors.GREEN_700)
                                    if is_paid
                                    else self.text_secondary
                                ),
                            ),
                            ft.Row(
                                spacing=6,
                                controls=[
                                    ft.IconButton(
                                        icon=Icons.DELETE_OUTLINE_ROUNDED,
                                        icon_size=18,
                                        icon_color=Colors.RED_400,
                                        tooltip="Sabit Gider Tanımını Sil",
                                        on_click=lambda e, fid=item[
                                            "id"
                                        ]: self.handle_delete_fixed_expense(fid),
                                    ),
                                    make_button(
                                        text=(
                                            "Bu Ay Ödendi"
                                            if is_paid
                                            else "Bu Ay Öde"
                                        ),
                                        icon=(
                                            Icons.CHECK_ROUNDED
                                            if is_paid
                                            else Icons.PAYMENT_ROUNDED
                                        ),
                                        disabled=is_paid,
                                        bgcolor=Colors.TEAL_600,
                                        color=Colors.WHITE,
                                        on_click=lambda e, fid=item[
                                            "id"
                                        ]: self.handle_pay_fixed_expense(fid),
                                    ),
                                ],
                            ),
                        ],
                    ),
                ],
            ),
        )

    def handle_pay_fixed_expense(self, fixed_id: int) -> None:
        """Sabit gideri seçili ayın giderlerine işler."""
        if self.db.pay_fixed_expense(fixed_id, self.selected_period):
            self.show_snackbar(
                f"Sabit gider {format_period_label(self.selected_period)} bütçesine işlendi!",
                Colors.GREEN_600,
            )
            self.refresh_all()

    def handle_pay_all_fixed(self) -> None:
        """Seçili aydaki tüm ödenmemiş sabit giderleri tek seferde öder."""
        count = self.db.pay_all_unpaid_fixed_expenses(self.selected_period)
        if count > 0:
            self.show_snackbar(
                f"{count} adet sabit gider {format_period_label(self.selected_period)} ayına işlendi!",
                Colors.GREEN_600,
            )
            self.refresh_all()

    def handle_delete_fixed_expense(self, fixed_id: int) -> None:
        """Sabit gider tanımını siler."""
        self.db.delete_fixed_expense(fixed_id)
        self.show_snackbar("Sabit gider tanımı silindi.", Colors.BLUE_GREY_700)
        self.refresh_all()

    # =====================================================================
    # 5. EKRAN 3: KREDİ VE TAKSİT TAKİP MODÜLÜ
    # =====================================================================
    def build_installments_view(self) -> ft.Control:
        """
        Kredi ve Taksit Takip Modülü:
        - Kredi/Borç adı, toplam taksit, kaçıncı taksitte olduğu,
          aylık tutar ve bitiş tarihinin listelendiği şık kartlar.
        """
        installments = self.db.get_installments()

        monthly_burden = sum(
            float(i["monthly_amount"])
            for i in installments
            if int(i["paid_installments"]) < int(i["total_installments"])
        )
        remaining_debt = sum(
            (int(i["total_installments"]) - int(i["paid_installments"]))
            * float(i["monthly_amount"])
            for i in installments
            if int(i["paid_installments"]) < int(i["total_installments"])
        )

        summary_banner = ft.Container(
            border_radius=20,
            padding=Padding.all(18),
            gradient=ft.LinearGradient(
                begin=ALIGN_TOP_LEFT,
                end=ALIGN_BOTTOM_RIGHT,
                colors=["#3730A3", "#312E81", "#1E1B4B"],
            ),
            content=ft.Column(
                spacing=12,
                controls=[
                    ft.Row(
                        alignment=MainAxisAlignment.SPACE_BETWEEN,
                        controls=[
                            ft.Column(
                                spacing=2,
                                controls=[
                                    ft.Text(
                                        "AYLIK TAKSİT YÜKÜ",
                                        size=11,
                                        color=WHITE_70,
                                        weight=FontWeight.W_600,
                                    ),
                                    ft.Text(
                                        format_currency(monthly_burden),
                                        size=26,
                                        weight=FontWeight.BOLD,
                                        color=Colors.WHITE,
                                    ),
                                ],
                            ),
                            make_button(
                                text="+ Yeni Taksit",
                                bgcolor=Colors.INDIGO_500,
                                color=Colors.WHITE,
                                on_click=lambda e: self.open_installment_modal(),
                            ),
                        ],
                    ),
                    ft.Divider(height=1, color=WHITE_24),
                    ft.Row(
                        alignment=MainAxisAlignment.SPACE_BETWEEN,
                        controls=[
                            ft.Text(
                                f"Toplam Kalan Taksit Borcu: {format_currency(remaining_debt)}",
                                size=12,
                                color=Colors.WHITE,
                                weight=FontWeight.W_500,
                            ),
                            ft.Text(
                                f"{len(installments)} Kayıt",
                                size=12,
                                color=WHITE_70,
                            ),
                        ],
                    ),
                ],
            ),
        )

        cards = []
        if not installments:
            cards.append(
                ft.Container(
                    padding=Padding.all(28),
                    border_radius=16,
                    bgcolor=self.card_color,
                    border=Border.all(1, self.border_color),
                    alignment=ALIGN_CENTER,
                    content=ft.Column(
                        horizontal_alignment=CrossAxisAlignment.CENTER,
                        spacing=8,
                        controls=[
                            ft.Icon(
                                Icons.CREDIT_SCORE_OUTLINED,
                                size=42,
                                color=self.text_secondary,
                            ),
                            ft.Text(
                                "Kayıtlı kredi veya taksit bulunmuyor.",
                                size=14,
                                weight=FontWeight.W_500,
                                color=self.text_primary,
                            ),
                            ft.Text(
                                "Kredi kartı taksitlerinizi veya kredi ödemelerinizi buradan takip edebilirsiniz.",
                                size=12,
                                color=self.text_secondary,
                                text_align=ft.TextAlign.CENTER,
                            ),
                        ],
                    ),
                )
            )
        else:
            for inst in installments:
                cards.append(self._build_installment_card(inst))

        return ft.ListView(
            expand=True,
            spacing=14,
            padding=Padding.only(bottom=12),
            controls=[
                summary_banner,
                ft.Text(
                    "Kredi ve Taksit Listesi",
                    size=14,
                    weight=FontWeight.BOLD,
                    color=self.text_primary,
                ),
                ft.Column(spacing=10, controls=cards),
            ],
        )

    def _build_installment_card(self, inst: dict) -> ft.Control:
        """Tek bir kredi/taksit kartını ilerleme çubuğu ve ödeme butonu ile oluşturur."""
        total = max(int(inst["total_installments"]), 1)
        paid = int(inst["paid_installments"])
        monthly = float(inst["monthly_amount"])
        remaining_count = max(total - paid, 0)
        remaining_amount = remaining_count * monthly
        progress = min(max(paid / total, 0.0), 1.0)
        is_completed = paid >= total

        status_color = Colors.GREEN_500 if is_completed else Colors.INDIGO_400

        return ft.Container(
            border_radius=16,
            padding=Padding.all(16),
            bgcolor=self.card_color,
            border=Border.all(1, self.border_color),
            content=ft.Column(
                spacing=10,
                controls=[
                    ft.Row(
                        alignment=MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Row(
                                spacing=10,
                                expand=True,
                                controls=[
                                    ft.Container(
                                        width=38,
                                        height=38,
                                        border_radius=10,
                                        bgcolor=status_color,
                                        alignment=ALIGN_CENTER,
                                        content=ft.Icon(
                                            (
                                                Icons.CHECK_CIRCLE_OUTLINE_ROUNDED
                                                if is_completed
                                                else Icons.CALENDAR_MONTH_ROUNDED
                                            ),
                                            color=Colors.WHITE,
                                            size=20,
                                        ),
                                    ),
                                    ft.Column(
                                        spacing=2,
                                        expand=True,
                                        controls=[
                                            ft.Text(
                                                inst["title"],
                                                size=15,
                                                weight=FontWeight.BOLD,
                                                color=self.text_primary,
                                            ),
                                            ft.Text(
                                                f"Bitiş Tarihi: {inst['end_date']}",
                                                size=11,
                                                color=self.text_secondary,
                                            ),
                                        ],
                                    ),
                                ],
                            ),
                            ft.Container(
                                padding=Padding.symmetric(horizontal=10, vertical=4),
                                border_radius=10,
                                bgcolor=(
                                    Colors.GREEN_900
                                    if is_completed
                                    else Colors.INDIGO_900
                                ),
                                content=ft.Text(
                                    (
                                        "Tamamlandı"
                                        if is_completed
                                        else f"{paid} / {total}. Taksit"
                                    ),
                                    size=11,
                                    weight=FontWeight.BOLD,
                                    color=Colors.WHITE,
                                ),
                            ),
                        ],
                    ),
                    ft.ProgressBar(
                        value=progress,
                        color=status_color,
                        bgcolor=self.border_color,
                        height=7,
                        border_radius=4,
                    ),
                    ft.Row(
                        alignment=MainAxisAlignment.SPACE_BETWEEN,
                        controls=[
                            ft.Column(
                                spacing=1,
                                controls=[
                                    ft.Text(
                                        "Aylık Taksit Tutarı",
                                        size=11,
                                        color=self.text_secondary,
                                    ),
                                    ft.Text(
                                        format_currency(monthly),
                                        size=14,
                                        weight=FontWeight.BOLD,
                                        color=self.text_primary,
                                    ),
                                ],
                            ),
                            ft.Column(
                                spacing=1,
                                horizontal_alignment=CrossAxisAlignment.END,
                                controls=[
                                    ft.Text(
                                        f"Kalan Borç ({remaining_count} Taksit)",
                                        size=11,
                                        color=self.text_secondary,
                                    ),
                                    ft.Text(
                                        format_currency(remaining_amount),
                                        size=14,
                                        weight=FontWeight.BOLD,
                                        color=(
                                            (Colors.GREEN_400 if self.is_dark else Colors.GREEN_700)
                                            if is_completed
                                            else (Colors.AMBER_400 if self.is_dark else Colors.AMBER_800)
                                        ),
                                    ),
                                ],
                            ),
                        ],
                    ),
                    ft.Row(
                        alignment=MainAxisAlignment.END,
                        spacing=8,
                        controls=[
                            ft.IconButton(
                                icon=Icons.DELETE_OUTLINE_ROUNDED,
                                icon_size=19,
                                icon_color=Colors.RED_400,
                                tooltip="Taksit Kaydını Sil",
                                on_click=lambda e, iid=inst[
                                    "id"
                                ]: self.handle_delete_installment(iid),
                            ),
                            make_button(
                                text=(
                                    "Borç Bitti"
                                    if is_completed
                                    else "Taksit Öde (+1)"
                                ),
                                icon=(
                                    Icons.CHECK_ROUNDED
                                    if is_completed
                                    else Icons.PAYMENT_ROUNDED
                                ),
                                disabled=is_completed,
                                bgcolor=Colors.TEAL_600,
                                color=Colors.WHITE,
                                on_click=lambda e, iid=inst[
                                    "id"
                                ]: self.handle_pay_installment(iid),
                            ),
                        ],
                    ),
                ],
            ),
        )

    def handle_pay_installment(self, inst_id: int) -> None:
        """Taksit sayacını 1 artırır ve tutarı seçili ayın gideri olarak bütçeden düşer."""
        if self.db.pay_installment_step(inst_id, self.selected_period):
            self.show_snackbar(
                f"Taksit ödendi ve {format_period_label(self.selected_period)} giderlerine işlendi!",
                Colors.GREEN_600,
            )
            self.refresh_all()

    def handle_delete_installment(self, inst_id: int) -> None:
        """Taksit kaydını siler."""
        self.db.delete_installment(inst_id)
        self.show_snackbar("Taksit kaydı silindi.", Colors.BLUE_GREY_700)
        self.refresh_all()

    # =====================================================================
    # 6. EKRAN 4: BİRİKİM KASASI MODÜLÜ
    # =====================================================================
    def build_savings_view(self) -> ft.Control:
        """
        Birikim Kasası Modülü:
        - Kullanıcının ana bütçesinden ayırıp kenara koyduğu birikimlerin tutulduğu
          ve artırılıp/azaltılabildiği ayrı alan.
        """
        summary = self.db.get_budget_summary(self.selected_period)
        total_savings = summary["savings"]
        net_wallet = summary["net_wallet"]
        savings_txs = self.db.get_transactions(tx_type="birikim", limit=50)

        vault_card = ft.Container(
            border_radius=22,
            padding=Padding.all(20),
            gradient=ft.LinearGradient(
                begin=ALIGN_TOP_LEFT,
                end=ALIGN_BOTTOM_RIGHT,
                colors=["#B45309", "#92400E", "#78350F"],
            ),
            content=ft.Column(
                spacing=14,
                controls=[
                    ft.Row(
                        alignment=MainAxisAlignment.SPACE_BETWEEN,
                        controls=[
                            ft.Row(
                                spacing=8,
                                controls=[
                                    ft.Icon(
                                        Icons.SAVINGS_ROUNDED,
                                        color=Colors.AMBER_200,
                                        size=22,
                                    ),
                                    ft.Text(
                                        "BİRİKİM KASASI TOPLAMI",
                                        size=12,
                                        weight=FontWeight.BOLD,
                                        color=Colors.AMBER_100,
                                    ),
                                ],
                            ),
                            ft.Container(
                                padding=Padding.symmetric(horizontal=8, vertical=3),
                                border_radius=8,
                                bgcolor=WHITE_12,
                                content=ft.Text(
                                    f"Bu Ay Net: {format_currency(net_wallet)}",
                                    size=11,
                                    color=Colors.WHITE,
                                ),
                            ),
                        ],
                    ),
                    ft.Text(
                        format_currency(total_savings),
                        size=34,
                        weight=FontWeight.BOLD,
                        color=Colors.WHITE,
                    ),
                    ft.Text(
                        "Ana bütçenizden ayırıp kenara koyduğunuz güvendeki birikimleriniz.",
                        size=12,
                        color=WHITE_70,
                    ),
                    ft.Row(
                        spacing=10,
                        controls=[
                            make_button(
                                expand=True,
                                text="Birikim Ekle (+)",
                                icon=Icons.ADD_CIRCLE_OUTLINE_ROUNDED,
                                bgcolor=Colors.GREEN_600,
                                color=Colors.WHITE,
                                on_click=lambda e: self.open_savings_modal(
                                    is_deposit=True
                                ),
                            ),
                            make_button(
                                expand=True,
                                text="Kasadan Çek (-)",
                                icon=Icons.REMOVE_CIRCLE_OUTLINE_ROUNDED,
                                bgcolor=Colors.RED_600,
                                color=Colors.WHITE,
                                on_click=lambda e: self.open_savings_modal(
                                    is_deposit=False
                                ),
                            ),
                        ],
                    ),
                ],
            ),
        )

        history_items = []
        if not savings_txs:
            history_items.append(
                ft.Container(
                    padding=Padding.all(26),
                    border_radius=16,
                    bgcolor=self.card_color,
                    border=Border.all(1, self.border_color),
                    alignment=ALIGN_CENTER,
                    content=ft.Column(
                        horizontal_alignment=CrossAxisAlignment.CENTER,
                        spacing=8,
                        controls=[
                            ft.Icon(
                                Icons.LOCK_CLOCK_OUTLINED,
                                size=40,
                                color=self.text_secondary,
                            ),
                            ft.Text(
                                "Birikim kasanızda henüz işlem yok.",
                                size=14,
                                weight=FontWeight.W_500,
                                color=self.text_primary,
                            ),
                            ft.Text(
                                "'Birikim Ekle (+)' butonuyla ana bütçenizden kenara para ayırabilirsiniz.",
                                size=12,
                                color=self.text_secondary,
                                text_align=ft.TextAlign.CENTER,
                            ),
                        ],
                    ),
                )
            )
        else:
            for tx in savings_txs:
                history_items.append(self._build_transaction_tile(tx))

        return ft.ListView(
            expand=True,
            spacing=14,
            padding=Padding.only(bottom=12),
            controls=[
                vault_card,
                ft.Text(
                    "Birikim Kasası Hareketleri",
                    size=14,
                    weight=FontWeight.BOLD,
                    color=self.text_primary,
                ),
                ft.Column(spacing=8, controls=history_items),
            ],
        )

    # =====================================================================
    # 7. FORM MODALLARI (GELİR, HARCAMA, SABİT GİDER, TAKSİT, BİRİKİM)
    # =====================================================================
    def open_transaction_modal(self, tx_type: str) -> None:
        """Seçili ay için Gelir veya Harcama Ekleme Form Penceresi."""
        is_income = tx_type == "gelir"
        period_label = format_period_label(self.selected_period)
        title_text = (
            f"Gelir Ekle ({period_label})"
            if is_income
            else f"Harcama Ekle ({period_label})"
        )
        categories = self.INCOME_CATEGORIES if is_income else self.EXPENSE_CATEGORIES

        amount_field = ft.TextField(
            label="Tutar (₺)",
            hint_text="Örn: 2500",
            keyboard_type=ft.KeyboardType.NUMBER,
            autofocus=True,
            border_radius=12,
        )

        category_dropdown = ft.Dropdown(
            label="Kategori Seçin",
            value=categories[0],
            options=[make_dropdown_option(c) for c in categories],
        )

        desc_field = ft.TextField(
            label="Açıklama (İsteğe Bağlı)",
            hint_text="Örn: Maaş ödemesi / Market alışverişi",
            border_radius=12,
        )

        error_text = ft.Text("", color=Colors.RED_400, size=12, visible=False)

        def save_tx(e):
            raw_val = (amount_field.value or "").replace(",", ".").strip()
            try:
                val = float(raw_val)
                if val <= 0:
                    raise ValueError()
            except ValueError:
                error_text.value = "Lütfen sıfırdan büyük geçerli bir tutar girin."
                error_text.visible = True
                self.page.update()
                return

            cat = category_dropdown.value or categories[0]
            desc = desc_field.value or ""
            self.db.add_transaction(
                tx_type=tx_type,
                category=cat,
                amount=val,
                description=desc,
                period=self.selected_period,
            )
            self.close_dialog(dialog)
            self.show_snackbar(
                f"{format_currency(val)} tutarında {'gelir' if is_income else 'harcama'} ({period_label}) eklendi!",
                Colors.GREEN_600 if is_income else Colors.RED_600,
            )
            self.refresh_all()

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(title_text, weight=FontWeight.BOLD, size=17),
            content=ft.Container(
                width=340,
                content=ft.Column(
                    tight=True,
                    spacing=12,
                    controls=[
                        amount_field,
                        category_dropdown,
                        desc_field,
                        error_text,
                    ],
                ),
            ),
            actions=[
                make_text_button(
                    "İptal", on_click=lambda e: self.close_dialog(dialog)
                ),
                make_button(
                    text="Kaydet",
                    bgcolor=Colors.GREEN_600 if is_income else Colors.RED_600,
                    color=Colors.WHITE,
                    on_click=save_tx,
                ),
            ],
            actions_alignment=MainAxisAlignment.END,
        )

        self.open_dialog(dialog)

    def open_fixed_expense_modal(self) -> None:
        """
        Her Ay Ödenen Sabit Gider Ekleme Form Penceresi.
        Kullanıcı gider başlığı, kategori, aylık sabit tutar ve ödeme gününü girer.
        İsterse 'Bu ayın giderlerine de hemen işle' seçeneğini işaretleyebilir.
        """
        title_field = ft.TextField(
            label="Sabit Gider Adı",
            hint_text="Örn: Ev Kirası / Ev İnterneti / Aidat",
            autofocus=True,
            border_radius=12,
        )

        category_dropdown = ft.Dropdown(
            label="Kategori",
            value=self.EXPENSE_CATEGORIES[0],
            options=[make_dropdown_option(c) for c in self.EXPENSE_CATEGORIES],
        )

        amount_field = ft.TextField(
            label="Aylık Sabit Tutar (₺)",
            hint_text="Örn: 15000",
            keyboard_type=ft.KeyboardType.NUMBER,
            border_radius=12,
            expand=True,
        )

        day_field = ft.TextField(
            label="Ödeme Günü (1-31)",
            value="1",
            keyboard_type=ft.KeyboardType.NUMBER,
            border_radius=12,
            width=125,
        )

        pay_now_checkbox = ft.Checkbox(
            label=f"{format_period_label(self.selected_period)} ayında ödendi olarak işle",
            value=True,
        )

        error_text = ft.Text("", color=Colors.RED_400, size=12, visible=False)

        def save_fixed(e):
            title = (title_field.value or "").strip()
            if not title:
                error_text.value = "Lütfen sabit gider adını girin."
                error_text.visible = True
                self.page.update()
                return

            try:
                val = float((amount_field.value or "").replace(",", ".").strip())
                day_val = int((day_field.value or "1").strip())
                if val <= 0 or day_val < 1 or day_val > 31:
                    raise ValueError()
            except ValueError:
                error_text.value = (
                    "Lütfen geçerli bir aylık tutar ve ödeme günü (1-31) girin."
                )
                error_text.visible = True
                self.page.update()
                return

            cat = category_dropdown.value or self.EXPENSE_CATEGORIES[0]
            fixed_id = self.db.add_fixed_expense(
                title=title,
                category=cat,
                amount=val,
                payment_day=day_val,
            )

            if pay_now_checkbox.value:
                self.db.pay_fixed_expense(fixed_id, self.selected_period)

            self.close_dialog(dialog)
            self.show_snackbar(
                f"'{title}' aylık sabit giderlere eklendi!", Colors.ORANGE_600
            )
            self.refresh_all()

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(
                "Her Ay Ödenen Sabit Gider Ekle", weight=FontWeight.BOLD, size=17
            ),
            content=ft.Container(
                width=340,
                content=ft.Column(
                    tight=True,
                    spacing=12,
                    controls=[
                        title_field,
                        category_dropdown,
                        ft.Row(
                            spacing=10,
                            controls=[amount_field, day_field],
                        ),
                        pay_now_checkbox,
                        error_text,
                    ],
                ),
            ),
            actions=[
                make_text_button(
                    "İptal", on_click=lambda e: self.close_dialog(dialog)
                ),
                make_button(
                    text="Kaydet",
                    bgcolor=Colors.ORANGE_600,
                    color=Colors.WHITE,
                    on_click=save_fixed,
                ),
            ],
            actions_alignment=MainAxisAlignment.END,
        )

        self.open_dialog(dialog)

    def open_installment_modal(self) -> None:
        """Kredi / Taksit Ekleme Form Penceresi."""
        title_field = ft.TextField(
            label="Kredi / Taksit Başlığı",
            hint_text="Örn: Telefon Taksiti / İhtiyaç Kredisi",
            autofocus=True,
            border_radius=12,
        )

        monthly_field = ft.TextField(
            label="Aylık Taksit Tutarı (₺)",
            hint_text="Örn: 3250",
            keyboard_type=ft.KeyboardType.NUMBER,
            border_radius=12,
        )

        total_inst_field = ft.TextField(
            label="Toplam Taksit Sayısı",
            value="12",
            keyboard_type=ft.KeyboardType.NUMBER,
            border_radius=12,
            expand=True,
        )

        paid_inst_field = ft.TextField(
            label="Ödenmiş Taksit",
            value="0",
            keyboard_type=ft.KeyboardType.NUMBER,
            border_radius=12,
            expand=True,
        )

        default_end = (datetime.now() + timedelta(days=365)).strftime("%d.%m.%Y")
        end_date_field = ft.TextField(
            label="Bitiş Tarihi (GG.AA.YYYY)",
            value=default_end,
            hint_text="Örn: 15.10.2027",
            border_radius=12,
        )

        error_text = ft.Text("", color=Colors.RED_400, size=12, visible=False)

        def save_inst(e):
            title = (title_field.value or "").strip()
            if not title:
                error_text.value = "Lütfen kredi veya taksit adını girin."
                error_text.visible = True
                self.page.update()
                return

            try:
                monthly_val = float(
                    (monthly_field.value or "").replace(",", ".").strip()
                )
                total_val = int((total_inst_field.value or "0").strip())
                paid_val = int((paid_inst_field.value or "0").strip())
                if (
                    monthly_val <= 0
                    or total_val <= 0
                    or paid_val < 0
                    or paid_val > total_val
                ):
                    raise ValueError()
            except ValueError:
                error_text.value = (
                    "Lütfen taksit sayılarını ve aylık tutarı doğru biçimde girin."
                )
                error_text.visible = True
                self.page.update()
                return

            end_date = (end_date_field.value or default_end).strip()
            self.db.add_installment(
                title=title,
                total_installments=total_val,
                paid_installments=paid_val,
                monthly_amount=monthly_val,
                end_date=end_date,
            )
            self.close_dialog(dialog)
            self.show_snackbar(
                f"'{title}' taksit takibine eklendi!", Colors.INDIGO_500
            )
            self.refresh_all()

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Yeni Kredi / Taksit Ekle", weight=FontWeight.BOLD, size=18),
            content=ft.Container(
                width=340,
                content=ft.Column(
                    tight=True,
                    spacing=12,
                    controls=[
                        title_field,
                        monthly_field,
                        ft.Row(
                            spacing=10,
                            controls=[total_inst_field, paid_inst_field],
                        ),
                        end_date_field,
                        error_text,
                    ],
                ),
            ),
            actions=[
                make_text_button(
                    "İptal", on_click=lambda e: self.close_dialog(dialog)
                ),
                make_button(
                    text="Kaydet",
                    bgcolor=Colors.INDIGO_500,
                    color=Colors.WHITE,
                    on_click=save_inst,
                ),
            ],
            actions_alignment=MainAxisAlignment.END,
        )

        self.open_dialog(dialog)

    def open_savings_modal(self, is_deposit: bool = True) -> None:
        """Birikim Kasasına Para Ekleme veya Kasadan Para Çekme Formu."""
        title_text = (
            "Birikim Kasasına Ekle (+)"
            if is_deposit
            else "Birikim Kasasından Çek (-)"
        )

        amount_field = ft.TextField(
            label="Tutar (₺)",
            hint_text="Örn: 1000",
            keyboard_type=ft.KeyboardType.NUMBER,
            autofocus=True,
            border_radius=12,
        )

        category_dropdown = ft.Dropdown(
            label="Birikim Hedefi / Türü",
            value=self.SAVINGS_CATEGORIES[0],
            options=[make_dropdown_option(c) for c in self.SAVINGS_CATEGORIES],
        )

        desc_field = ft.TextField(
            label="Açıklama (İsteğe Bağlı)",
            hint_text=(
                "Örn: Maaştan kenara ayrılan"
                if is_deposit
                else "Örn: Nakit ihtiyacı için cüzdana aktarım"
            ),
            border_radius=12,
        )

        error_text = ft.Text("", color=Colors.RED_400, size=12, visible=False)

        def save_savings(e):
            raw_val = (amount_field.value or "").replace(",", ".").strip()
            try:
                val = float(raw_val)
                if val <= 0:
                    raise ValueError()
            except ValueError:
                error_text.value = "Lütfen sıfırdan büyük geçerli bir tutar girin."
                error_text.visible = True
                self.page.update()
                return

            summary = self.db.get_budget_summary(self.selected_period)
            if not is_deposit and val > summary["savings"]:
                error_text.value = f"Kasada yeterli birikim yok! Mevcut: {format_currency(summary['savings'])}"
                error_text.visible = True
                self.page.update()
                return

            signed_amount = val if is_deposit else -val
            cat = category_dropdown.value or self.SAVINGS_CATEGORIES[0]
            default_desc = (
                "Cüzdandan Birikim Kasasına Aktarım"
                if is_deposit
                else "Birikim Kasasından Cüzdana İade"
            )
            desc = (desc_field.value or "").strip() or default_desc

            self.db.add_transaction(
                tx_type="birikim",
                category=cat,
                amount=signed_amount,
                description=desc,
                period=self.selected_period,
            )
            self.close_dialog(dialog)
            self.show_snackbar(
                (
                    f"{format_currency(val)} birikim kasasına eklendi!"
                    if is_deposit
                    else f"{format_currency(val)} kasadan cüzdana aktarıldı!"
                ),
                Colors.AMBER_700,
            )
            self.refresh_all()

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(title_text, weight=FontWeight.BOLD, size=18),
            content=ft.Container(
                width=340,
                content=ft.Column(
                    tight=True,
                    spacing=12,
                    controls=[
                        amount_field,
                        category_dropdown,
                        desc_field,
                        error_text,
                    ],
                ),
            ),
            actions=[
                make_text_button(
                    "İptal", on_click=lambda e: self.close_dialog(dialog)
                ),
                make_button(
                    text="Onayla",
                    bgcolor=Colors.GREEN_600 if is_deposit else Colors.RED_600,
                    color=Colors.WHITE,
                    on_click=save_savings,
                ),
            ],
            actions_alignment=MainAxisAlignment.END,
        )

        self.open_dialog(dialog)

    # =====================================================================
    # 8. EKRAN YENİLEME VE DURUM GÜNCELLEME
    # =====================================================================
    def refresh_all(self) -> None:
        """Aktif sekmeye, seçili aya ve temaya göre tüm bileşenleri yeniden çizer."""
        self.page.bgcolor = self.bg_color
        self.main_layout.bgcolor = self.bg_color
        self.header_bar.bgcolor = self.card_color

        self.period_bar_container.content = self.build_period_selector_bar()

        if self.current_tab_index == 0:
            self.body_container.content = self.build_dashboard_view()
        elif self.current_tab_index == 1:
            self.body_container.content = self.build_fixed_expenses_view()
        elif self.current_tab_index == 2:
            self.body_container.content = self.build_installments_view()
        else:
            self.body_container.content = self.build_savings_view()

        self.nav_bar_container.content = self.build_bottom_nav()
        self.page.update()


def main(page: ft.Page):
    """Flet uygulama giriş noktası."""
    PersonalSafeApp(page)


if __name__ == "__main__":
    if hasattr(ft, "run"):
        ft.run(main)
    else:
        ft.app(target=main)
