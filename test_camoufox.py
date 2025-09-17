# test_camoufox.py (registro con formulario estilo Roblox) - ESPERAR "Inicio" - PostgreSQL
import os
import random
import string
import time
from camoufox.sync_api import Camoufox
import psycopg2

# ---------- Config ----------
TARGET = "https://www.roblox.com/es"  # URL del formulario de registro
BASE_PREFIX = "youngceoio"
NUM_ACCOUNTS = 2
HEADLESS = True
PAUSE_BETWEEN = 1
ENSURE_UNIQUE = True

# ---------- Helpers ----------
def gen_creds(prefix=BASE_PREFIX, pwd_len=12):
    user = f"{prefix}_{''.join(random.choices(string.ascii_lowercase + string.digits, k=6))}"
    pwd = ''.join(random.choices(string.ascii_letters + string.digits + "!@#$%", k=pwd_len))
    return user, pwd

def make_unique_username(desired, existing_set):
    if desired not in existing_set:
        return desired
    i = 1
    while True:
        candidate = f"{desired}_{i}"
        if candidate not in existing_set:
            return candidate
        i += 1

def wait_for_inicio_or_success(page, target_url, idx, timeout=20000):
    start = time.time()
    checks = [
        'text="Inicio"',
        'a:has-text("Inicio")',
        'button:has-text("Inicio")',
        'text=/\\bBienvenid|Welcome|Cuenta creada|account created\\b/i',
        'div.alert-success',
        'div.notice-success'
    ]
    poll_interval = 0.5
    deadline = start + (timeout / 1000.0)

    while time.time() < deadline:
        try:
            if page.url and page.url != target_url:
                return True
        except Exception:
            pass

        for sel in checks:
            try:
                el = page.query_selector(sel)
                if el:
                    return True
            except Exception:
                pass

        time.sleep(poll_interval)

    return False

# ---------- Main ----------
def main():
    DATABASE_URL = os.environ.get("DATABASE_URL")
    if not DATABASE_URL:
        print("ERROR: No se encontró la variable de entorno DATABASE_URL.")
        return

    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        # Crear tabla si no existe
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            id SERIAL PRIMARY KEY,
            username TEXT NOT NULL,
            password TEXT NOT NULL
        )
        """)
        conn.commit()
    except Exception as e:
        print("ERROR conectando a la base de datos:", e)
        return

    creds_to_use = [gen_creds(prefix=BASE_PREFIX, pwd_len=10) for _ in range(NUM_ACCOUNTS)]

    # Leer usuarios existentes de DB
    existing_users = set()
    try:
        cursor.execute("SELECT username FROM accounts")
        rows = cursor.fetchall()
        existing_users = set([r[0] for r in rows])
    except Exception:
        pass

    created_this_run = set()
    created_ordered = []

    print(f"Iniciando Camoufox (headless={HEADLESS}), creando {len(creds_to_use)} cuentas con prefijo '{BASE_PREFIX}'...")

    with Camoufox(
        headless=HEADLESS,
        humanize=True,
        i_know_what_im_doing=True,
        locale=["es-ES"],
        window=(1024, 768),
    ) as browser:
        for idx, (user, pwd) in enumerate(creds_to_use, start=1):
            original_user = user
            if ENSURE_UNIQUE:
                user = make_unique_username(user, existing_users.union(created_this_run))

            context = browser.new_context()
            page = context.new_page()

            try:
                # Navegar a la página
                try:
                    page.goto(TARGET, timeout=20000, wait_until="domcontentloaded")
                except Exception as e_goto:
                    print(f"[{idx}] warning: page.goto falló o tardó demasiado: {e_goto}")

                # Esperar input username
                try:
                    page.wait_for_selector("input#signup-username", timeout=8000)
                except Exception:
                    print(f"[{idx}] No se encontró input#signup-username; saltando intento.")
                    context.close()
                    time.sleep(PAUSE_BETWEEN)
                    continue

                # Fecha de nacimiento
                try:
                    page.select_option("#DayDropdown", "15")
                    page.select_option("#MonthDropdown", "Jun")
                    page.select_option("#YearDropdown", "2005")
                except Exception:
                    pass

                # Usuario y contraseña
                try:
                    page.fill("input#signup-username", user)
                    page.fill("input#signup-password", pwd)
                except Exception as e_fill:
                    print(f"[{idx}] error rellenando username/password: {e_fill}")
                    context.close()
                    time.sleep(PAUSE_BETWEEN)
                    continue

                # Género
                try:
                    page.click("button#MaleButton", timeout=3000)
                except Exception:
                    pass

                # Términos y condiciones
                try:
                    checkbox = page.wait_for_selector("input#signup-checkbox", timeout=3000)
                    if checkbox:
                        page.check("input#signup-checkbox")
                        print(f"[{idx}] Checkbox de términos marcado.")
                except Exception:
                    pass

                # Click en registrarse
                signup_selectors = [
                    "button#signup-button",
                    "button.signup-button",
                    "button[aria-label='Registrarse']",
                    "button.btn-primary-md.signup-submit-button",
                ]

                clicked = False
                for sel in signup_selectors:
                    try:
                        button = page.wait_for_selector(sel, timeout=20000, state="visible")
                        if button:
                            page.click(sel)
                            print(f"[{idx}] Click en botón de registro con selector: {sel}")
                            clicked = True
                            break
                    except Exception:
                        continue

                if not clicked:
                    print(f"[{idx}] error: no se pudo localizar/clicar el botón de registro")
                    context.close()
                    time.sleep(PAUSE_BETWEEN)
                    continue

                # Esperar éxito
                success = wait_for_inicio_or_success(page, TARGET, idx, timeout=20000)

                if success:
                    try:
                        cursor.execute(
                            "INSERT INTO accounts (username, password) VALUES (%s, %s)",
                            (user, pwd)
                        )
                        conn.commit()
                        created_this_run.add(user)
                        created_ordered.append((user, pwd))
                        print(f"[{idx}] '{original_user}' creado y guardado en DB como '{user}'.")
                    except Exception as e_db:
                        print(f"[{idx}] ERROR guardando en DB: {e_db}")
                else:
                    print(f"[{idx}] posible fallo al crear {user}: no apareció 'Inicio' ni indicador de éxito.")

            except Exception as e:
                print(f"[{idx}] excepción durante la creación de {user}: {e}")

            finally:
                try:
                    context.close()
                except Exception:
                    pass

            time.sleep(PAUSE_BETWEEN)

    print("\nProceso terminado. Usuarios creados en esta ejecución:")
    for u, p in created_ordered:
        print(" -", u, ":", p)

    cursor.close()
    conn.close()


if __name__ == "__main__":
    if not TARGET:
        print("ATENCIÓN: no has configurado TARGET. Edita el script y pon la URL de tu formulario.")
    main()

