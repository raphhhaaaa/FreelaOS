import os
import time
import logging
import urllib.parse
from playwright.sync_api import sync_playwright
from backend.src.core.browser_manager import BrowserManager
from backend.src.modules.opportunities.repository import OpportunityRepository

opp_repo = OpportunityRepository()

logger = logging.getLogger(__name__)

class WorkanaCrawler:
    @staticmethod
    def executar(user_id: str, area_atuacao: str):
        if BrowserManager.is_cancelled(user_id):
            logger.info(f"[Workana] Execução cancelada antes de iniciar para {user_id}.")
            return []

        session_dir = os.path.join(os.getcwd(), "playwright_sessions", user_id, "workana")
        if not os.path.exists(session_dir):
            raise ValueError("Sessão da Workana não encontrada. Conecte sua conta nas configurações.")
            
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
                        logger.info(f"[Workana] Interrupção detectada. Cancelando buscas para {user_id}.")
                        return []

                    logger.info(f"[Workana] Buscando na área: ({area_atuacao})")
                    
                    # Mapeamento para as categorias nativas
                    mapa_categorias = {
                        "Desenvolvimento e TI": "it-programming",
                        "Design e Multimedia": "design-multimedia",
                        "Escrita e Tradução": "writing-translation",
                        "Marketing e Vendas": "sales-marketing",
                        "Suporte Administrativo": "admin-support"
                    }
                    
                    cat_slug = mapa_categorias.get(area_atuacao, "it-programming")
                    
                    links_data = []
                    for page_num in range(1, (2 + 1)):  # Ajuste para pegar 2 páginas
                        url_alvo = f"https://www.workana.com/jobs?category={cat_slug}&language=pt&page={page_num}"
                        page.goto(url_alvo)
                        
                        try:
                            page.wait_for_selector(".project-item", timeout=10000)
                        except Exception:
                            logger.info(f"[Workana] Nenhuma vaga encontrada para a área {area_atuacao} na página {page_num}.")
                            continue
                            
                        links_elements = page.locator(".project-item .project-title a")
                        count = links_elements.count()
                        logger.info(f"[Workana] Encontradas {count} vagas para {area_atuacao} na página {page_num}.")
                        
                        for i in range(count):
                            elem = links_elements.nth(i)
                            href = elem.get_attribute("href")
                            titulo = elem.inner_text().strip() or href
                            if href:
                                if not href.startswith("http"):
                                    href = "https://www.workana.com" + href
                                links_data.append({"url": href, "titulo": titulo})
                    
                    # Deduplicate based on URL while preserving order
                    seen = set()
                    unique_links = []
                    for item in links_data:
                        if item["url"] not in seen:
                            seen.add(item["url"])
                            unique_links.append(item)
                    
                    for item in unique_links:
                        if BrowserManager.is_cancelled(user_id):
                            break

                        link = item["url"]
                        titulo_vaga = item["titulo"]
                        # Extract job detail
                        try:
                            page.goto(link, timeout=15000, wait_until="domcontentloaded")
                            page.wait_for_timeout(1000)
                            # Extrai o texto da página da vaga. 
                            texto_vaga = page.inner_text("body")
                        except Exception as e:
                            logger.error(f"[Workana] Erro ao extrair texto da vaga {link}: {e}")
                            continue
                            
                        if texto_vaga:
                            # Tenta capturar a foto do cliente na página da Workana
                            foto_cliente = None
                            try:
                                avatar_elem = page.locator(".profile-photo img, .profile-photo a img, img[src*='cf.workana.com/logos'], .user-avatar img, .client-avatar img, .avatar img, .profile-image img, img[src*='avatar'], img[src*='user']")
                                if avatar_elem.count() > 0:
                                    for idx in range(avatar_elem.count()):
                                        img_node = avatar_elem.nth(idx)
                                        src = img_node.get_attribute("src") or img_node.get_attribute("data-src")
                                        if src and not src.startswith("data:") and "blank" not in src and "default" not in src and "sneak-peek-user" not in src:
                                            if src.startswith("//"):
                                                foto_cliente = f"https:{src}"
                                            elif src.startswith("/"):
                                                foto_cliente = f"https://www.workana.com{src}"
                                            else:
                                                foto_cliente = src
                                            break
                            except Exception as e:
                                logger.debug(f"[Workana] Não foi possível extrair foto do cliente: {e}")

                            resultados.append({
                                "plataforma": "Workana",
                                "titulo": titulo_vaga,
                                "url": link,
                                "texto_bruto": texto_vaga,
                                "cliente_foto_url": foto_cliente
                            })
                                
                            # Pausa amigável para não sobrecarregar o site
                            time.sleep(2)
                finally:
                    BrowserManager.unregister_browser(user_id, browser)
                    try:
                        browser.close()
                    except Exception:
                        pass
        except Exception as e:
            if BrowserManager.is_cancelled(user_id):
                logger.info(f"[Workana] Crawler encerrado com sucesso devido ao logout do usuário {user_id}.")
                return resultados
            logger.error(f"[Workana] Erro durante a execução do crawler: {e}")
            return resultados

        return resultados
