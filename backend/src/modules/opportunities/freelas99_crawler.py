import os
import urllib.parse
import logging
from playwright.sync_api import sync_playwright

from backend.src.core.browser_manager import BrowserManager

logger = logging.getLogger(__name__)

class Freelas99Crawler:
    @staticmethod
    def executar(user_id: str, area_atuacao: str, ignorar_exclusivos: bool = True, urls_existentes: set = None):
        if urls_existentes is None:
            urls_existentes = set()

        if BrowserManager.is_cancelled(user_id):
            logger.info(f"[99Freelas] Execução cancelada antes de iniciar para {user_id}.")
            return []

        session_dir = os.path.join(os.getcwd(), "playwright_sessions", user_id, "99freelas")
        if not os.path.exists(session_dir):
            raise ValueError("Sessão do 99Freelas não encontrada. Conecte sua conta nas configurações.")
            
        resultados = []
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch_persistent_context(
                    user_data_dir=session_dir,
                    headless=True,
                    args=["--disable-blink-features=AutomationControlled"]
                )
                BrowserManager.register_browser(user_id, browser)
                try:
                    page = browser.new_page()
                    
                    if BrowserManager.is_cancelled(user_id):
                        logger.info(f"[99Freelas] Interrupção detectada. Cancelando buscas para {user_id}.")
                        return []

                    logger.info(f"[99Freelas] Buscando na área: ({area_atuacao})")
                    
                    # Mapeamento para as categorias nativas
                    mapa_categorias = {
                        "Desenvolvimento e TI": "web-mobile-e-software",
                        "Design e Multimedia": "design-e-criacao",
                        "Escrita e Tradução": "escrita",
                        "Marketing e Vendas": "vendas-e-marketing",
                        "Suporte Administrativo": "suporte-administrativo"
                    }
                    
                    cat_slug = mapa_categorias.get(area_atuacao, "web-desenvolvimento")
                    for page_num in range(1, (3 + 1)):  # Ajuste para pegar 3 páginas
                        url_alvo = f"https://www.99freelas.com.br/projects?categoria={cat_slug}&page={page_num}"
                        
                        page.goto(url_alvo, timeout=20000)

                        try:
                            page.wait_for_selector(".result-list", timeout=5000)
                        except Exception:
                            logger.info(f"[99Freelas] Nenhuma vaga encontrada para a área {area_atuacao} na página {page_num}.")
                            continue

                        projetos = page.locator(".result-list li.result-item")
                        total = projetos.count()
                        logger.info(f"[99Freelas] Encontradas {total} vagas para {area_atuacao} na página {page_num}.")

                        for i in range(total):
                            if BrowserManager.is_cancelled(user_id):
                                break

                            projeto = projetos.nth(i)
                            titulo_elem = projeto.locator("h1.title")
                            if titulo_elem.count() == 0:
                                continue

                            link_tag = titulo_elem.locator("a")
                            if link_tag.count() == 0:
                                continue

                            titulo = link_tag.inner_text()
                            href = link_tag.get_attribute("href")
                            url_vaga = f"https://www.99freelas.com.br{href}"

                            # Tenta clicar em "Expandir" para ler o texto todo da vaga
                            expandir_btn = projeto.locator("text='Expandir'")
                            if expandir_btn.count() > 0:
                                try:
                                    expandir_btn.first.click()
                                    page.wait_for_timeout(800) # Espera a animação de expansão do site concluir
                                except Exception:
                                    pass

                            # Extração Profunda (Raw Text)
                            texto_bruto = projeto.inner_text()

                            # Lê todas as flags (Urgente, Destaque, Exclusivo)
                            flags_imgs = projeto.locator(".flags img")
                            lista_flags = []
                            for f in range(flags_imgs.count()):
                                alt_text = flags_imgs.nth(f).get_attribute("alt")
                                if alt_text:
                                    lista_flags.append(alt_text)

                            if lista_flags:
                                texto_bruto += f"\n[FLAGS ENCONTRADAS]: {', '.join(lista_flags)}"

                            # Verifica se é projeto exclusivo (ignoramos Urgente e Destaque aqui)
                            is_exclusivo = any("exclusivo" in f.lower() for f in lista_flags)

                            if ignorar_exclusivos and is_exclusivo:
                                logger.info(f"[99Freelas] Vaga ignorada (assinatura premium): {titulo}")
                                continue

                            # Tenta capturar a foto do cliente / autor da vaga entrando na página
                            foto_cliente = None

                            # OTIMIZAÇÃO: Só entra na página se a vaga for nova
                            if url_vaga not in urls_existentes:
                                try:
                                    vaga_page = browser.new_page()
                                    vaga_page.route("**/*", lambda route: route.abort() if route.request.resource_type in ["image", "stylesheet", "script", "font", "media"] else route.continue_())
                                    vaga_page.goto(url_vaga, timeout=10000, wait_until="domcontentloaded")

                                    avatar_elem = vaga_page.locator(".info-usuario.cliente .info-usuario-imagem img")
                                    if avatar_elem.count() > 0:
                                        for idx in range(avatar_elem.count()):
                                            img_node = avatar_elem.nth(idx)

                                            # Ignorar a foto do próprio usuário logado
                                            class_attr = img_node.get_attribute("class") or ""
                                            if "fotoUsuario" in class_attr:
                                                continue

                                            src = img_node.get_attribute("src") or img_node.get_attribute("data-src") or img_node.get_attribute("data-original")
                                            placeholder = img_node.get_attribute("data-placeholder")

                                            if src and not src.startswith("data:") and "blank" not in src:
                                                if "default.jpg" in src or (placeholder and src == placeholder):
                                                    break
                                                if src.startswith("//"):
                                                    foto_cliente = f"https:{src}"
                                                elif src.startswith("/"):
                                                        foto_cliente = f"https://www.99freelas.com.br{src}"
                                                else:
                                                    foto_cliente = src
                                                    break
                                        vaga_page.close()
                                except Exception as e:
                                        logger.debug(f"[99Freelas] Não foi possível extrair foto do cliente: {e}")
                                        try:
                                            vaga_page.close()
                                        except:
                                            pass

                                resultados.append({
                                    "plataforma": "99Freelas",
                                    "titulo": titulo,
                                    "url": url_vaga,
                                    "texto_bruto": texto_bruto,
                                    "cliente_foto_url": foto_cliente
                                })
                finally:
                    BrowserManager.unregister_browser(user_id, browser)
                    try:
                        browser.close()
                    except Exception:
                        pass
        except Exception as e:
            if BrowserManager.is_cancelled(user_id):
                logger.info(f"[99Freelas] Crawler encerrado com sucesso devido ao logout do usuário {user_id}.")
            else:
                logger.error(f"[99Freelas] Erro inesperado durante execução: {e}")
            return resultados

        return resultados
