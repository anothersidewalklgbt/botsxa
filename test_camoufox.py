# test_camoufox.py (registro con formulario estilo Roblox) - ESPERAR "Inicio"
import random
import string
import time
import os
import psycopg2
from camoufox.sync_api import Camoufox

# ---------- Config ----------
TARGET = "https://www.roblox.com/es"  # URL del formulario de registro
BASE_PREFIX = "youngceoio"
NUM_ACCOUNTS = 1
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
    creds_to_use = [gen_creds(prefix=BASE_PREFIX, pwd_len=10) for _ in range(NUM_ACCOUNTS)]

    # ---------- Conectar a PostgreSQL ----------
    DATABASE_URL = os.getenv("DATABASE_URL")
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    # Crear tabla si no existe
    cur.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            id SERIAL PRIMARY KEY,
            username TEXT NOT NULL,
            password TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        );
    """)
    conn.commit()

    # Leer usuarios existentes
    cur.execute("SELECT username FROM accounts;")
    existing_users = {row[0] for row in cur.fetchall()}

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
                try:
                    page.goto(TARGET, timeout=20000, wait_until="domcontentloaded")
                except Exception as e_goto:
                    print(f"[{idx}] warning: page.goto falló o tardó demasiado: {e_goto}")

                try:
                    page.wait_for_selector("input#signup-username", timeout=8000)
                except Exception:
                    print(f"[{idx}] No se encontró input#signup-username; saltando intento.")
                    context.close()
                    time.sleep(PAUSE_BETWEEN)
                    continue

                try:
                    page.select_option("#DayDropdown", "15")
                    page.select_option("#MonthDropdown", "Jun")
                    page.select_option("#YearDropdown", "2005")
                except Exception:
                    pass

                try:
                    page.fill("input#signup-username", user)
                    page.fill("input#signup-password", pwd)
                except Exception as e_fill:
                    print(f"[{idx}] error rellenando username/password: {e_fill}")
                    context.close()
                    time.sleep(PAUSE_BETWEEN)
                    continue

                try:
                    page.click("button#MaleButton", timeout=3000)
                except Exception:
                    pass

                try:
                    checkbox = page.wait_for_selector("input#signup-checkbox", timeout=3000)
                    if checkbox:
                        page.check("input#signup-checkbox")
                        print(f"[{idx}] Checkbox de términos marcado.")
                except Exception:
                    pass

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

                success = wait_for_inicio_or_success(page, TARGET, idx, timeout=20000)

                html = ""
                try:
                    html = page.content()[:200000]
                except Exception:
                    html = ""

                if not success:
                    try:
                        if page.url and page.url != TARGET:
                            success = True
                    except Exception:
                        pass

                if not success and html:
                    if any(k in html for k in ["Registrado OK.", "Registrado", "Registro completado", "Welcome", "Cuenta creada"]):
                        success = True

                if success:
                    # Guardar en PostgreSQL
                    cur.execute(
                        "INSERT INTO accounts (username, password) VALUES (%s, %s)",
                        (user, pwd)
                    )
                    conn.commit()
                    created_this_run.add(user)
                    created_ordered.append((user, pwd))
                    if user != original_user:
                        print(f"[{idx}] '{original_user}' ya existía → usando '{user}'. Guardado.")
                    else:
                        print(f"[{idx}] creado: {user} (guardado en DB)")
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

    print("\nProceso terminado. Usuarios guardados en la base de datos:")
    for u, p in created_ordered:
        print(" -", u, ":", p)

    cur.close()
    conn.close()

if __name__ == "__main__":
    if not TARGET:
        print("ATENCIÓN: no has configurado TARGET. Edita el script y pon la URL de tu formulario.")
    main()
