# test_camoufox.py (registro con formulario estilo Roblox) - ESPERAR "Inicio"
import csv
import random
import string
import time
import os
from camoufox.sync_api import Camoufox

# ---------- Config ----------
TARGET = "example.com"  # URL del formulario de registro
BASE_PREFIX = "youngceoio"
NUM_ACCOUNTS = 5
HEADLESS = True
CSV_FILE = "accounts.csv"
PAUSE_BETWEEN = 1
ENSURE_UNIQUE = True

# ---------- Helpers ----------
def gen_creds(prefix=BASE_PREFIX, pwd_len=12):
    user = f"{prefix}_{''.join(random.choices(string.ascii_lowercase + string.digits, k=6))}"
    pwd = ''.join(random.choices(string.ascii_letters + string.digits + "!@#$%", k=pwd_len))
    return user, pwd


def ensure_csv_header(path):
    try:
        with open(path, "x", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["username", "password"])
    except FileExistsError:
        pass


def read_existing_users_from_csv(path):
    users = set()
    if not os.path.exists(path):
        return users
    try:
        with open(path, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if "username" in row and row["username"]:
                    users.add(row["username"])
    except Exception:
        pass
    return users


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
    """
    Espera hasta que aparezca un indicador de 'inicio' o éxito después del submit.
    Indicadores:
      - elemento con texto "Inicio"
      - enlace o botón con texto "Inicio"
      - mensajes habituales ("Welcome", "Bienvenido", "Cuenta creada", etc.)
      - cambio de URL desde target_url
    Devuelve True si detecta éxito, False si timeout.
    """
    start = time.time()
    # Lista de selectores/texto a comprobar (en orden de preferencia)
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
        # 1) revisar cambio de URL rápido
        try:
            if page.url and page.url != target_url:
                return True
        except Exception:
            pass

        # 2) revisar los selectores/textos
        for sel in checks:
            try:
                # usamos wait_for_selector con timeout corto para comprobar existencia de forma no bloqueante
                el = page.query_selector(sel)
                if el:
                    return True
            except Exception:
                # algunos selectores tipo regex pueden lanzar; ignorar y seguir
                pass

        time.sleep(poll_interval)

    # Si llega aquí, no detectó 'Inicio' ni cambios en URL dentro del timeout
    return False


# ---------- Main ----------
def main():
    creds_to_use = [gen_creds(prefix=BASE_PREFIX, pwd_len=10) for _ in range(NUM_ACCOUNTS)]
    ensure_csv_header(CSV_FILE)

    existing_users = read_existing_users_from_csv(CSV_FILE)
    created_this_run = set()
    created_ordered = []

    print("CSV absoluto:", os.path.abspath(CSV_FILE))
    print(
        f"Iniciando Camoufox (headless={HEADLESS}), creando {len(creds_to_use)} "
        f"cuentas con prefijo '{BASE_PREFIX}'..."
    )

    with Camoufox(
        headless=HEADLESS,
        humanize=True,
        # block_images=True,  # desactivado para mejor performance y menor detección
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

                # Esperar hasta que aparezca el input username (si no aparece, saltamos)
                try:
                    page.wait_for_selector("input#signup-username", timeout=8000)
                except Exception:
                    print(f"[{idx}] No se encontró input#signup-username; saltando intento.")
                    try:
                        context.close()
                    except Exception:
                        pass
                    time.sleep(PAUSE_BETWEEN)
                    continue

                # Fecha de nacimiento (intento rápido; no crítico)
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
                    try:
                        context.close()
                    except Exception:
                        pass
                    time.sleep(PAUSE_BETWEEN)
                    continue

                # Género (opcional)
                try:
                    page.click("button#MaleButton", timeout=3000)
                except Exception:
                    pass

                # Términos y condiciones (checkbox)
                try:
                    checkbox = page.wait_for_selector("input#signup-checkbox", timeout=3000)
                    if checkbox:
                        page.check("input#signup-checkbox")
                        print(f"[{idx}] Checkbox de términos marcado.")
                except Exception:
                    pass

                # CLICK en registrarse: esperar hasta que el botón esté visible y clickeable
                signup_selectors = [
                    "button#signup-button",
                    "button.signup-button",
                    "button[aria-label='Registrarse']",
                    "button.btn-primary-md.signup-submit-button",
                ]

                clicked = False
                for sel in signup_selectors:
                    try:
                        # esperar dinámicamente a que el selector esté visible (máx 20s por selector)
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
                    try:
                        context.close()
                    except Exception:
                        pass
                    time.sleep(PAUSE_BETWEEN)
                    continue

                # DESPUÉS DEL SUBMIT: esperar hasta que aparezca "Inicio" u otro indicador
                success = wait_for_inicio_or_success(page, TARGET, idx, timeout=20000)

                # Guardar HTML reducido para diagnóstico (si se desea)
                html = ""
                try:
                    html = page.content()[:200000]
                except Exception:
                    html = ""

                # Si no detectó 'Inicio', aún revisar cambio de URL o mensajes de éxito
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
                    with open(CSV_FILE, "a", newline="", encoding="utf-8") as f:
                        writer = csv.writer(f)
                        writer.writerow([user, pwd])
                    created_this_run.add(user)
                    created_ordered.append((user, pwd))
                    if user != original_user:
                        print(f"[{idx}] '{original_user}' ya existía → usando '{user}'. Guardado.")
                    else:
                        print(f"[{idx}] creado: {user} (guardado en CSV)")
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

    print("\nProceso terminado. Credenciales guardadas en", os.path.abspath(CSV_FILE))
    print("Usuarios creados en esta ejecución:")
    for u, p in created_ordered:
        print(" -", u, ":", p)


if __name__ == "__main__":
    if not TARGET:
        print("ATENCIÓN: no has configurado TARGET. Edita el script y pon la URL de tu formulario.")
    ensure_csv_header(CSV_FILE)
    main()



