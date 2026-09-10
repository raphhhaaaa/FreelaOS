from backend.src.core.llm_client import generate_json
from backend.src.modules.opportunities.repository import OpportunityRepository, ProfileRepository, ClientRepository
from backend.src.core.llm_client import _get_active_llm

opp_repo = OpportunityRepository()
profile_repo = ProfileRepository()
client_repo = ClientRepository()

class AnalistaService:
    @staticmethod
    def avaliar_oportunidade(vaga_id: str, user_id: str) -> dict:
        vaga = opp_repo.get_opportunity(vaga_id)
        if not vaga:
            raise ValueError("Vaga não encontrada")

        perfil = profile_repo.get_profile(user_id)
        if not perfil:
            raise ValueError("Perfil de usuário não encontrado")

        prompt = f"""
        Você é o Analista IA, um agente rigoroso responsável por calcular o "Score de Compatibilidade" (0 a 100)
        de uma oportunidade de projeto freelancer em relação ao perfil do desenvolvedor.
        
        PERFIL DO DESENVOLVEDOR:
        - Habilidades Principais: {', '.join(perfil.get('habilidades', []))}
        - Senioridade: {perfil.get('senioridade', 'Não informada')}
        - Valor Mínimo por Hora: {perfil.get('valor_hora_minimo', 0)}
        - Valor Mínimo por Projeto Fechado: {perfil.get('valor_projeto_minimo', 0)}
        - Moeda Base: {perfil.get('moeda_base', 'BRL')}
        - Biografia: {perfil.get('bio', '')}

        OPORTUNIDADE ENCONTRADA:
        - Título: {vaga.get('titulo', '')}
        - Descrição: {vaga.get('descricao', '')}
        - Tecnologias (Stack): {', '.join(vaga.get('stack', []))}
        - Orçamento Indicado: {vaga.get('orcamento', 0)}
        - Prazo: {vaga.get('prazo', '')}
        - Plataforma: {vaga.get('plataforma', '')}

        INSTRUÇÕES DA ANÁLISE:
        Calcule uma nota de 0 a 100 considerando:
        1. Fit Técnico: A Stack bate com as habilidades do desenvolvedor?
        2. Fit Financeiro: O orçamento está de acordo com o mínimo que ele aceita? (observação importante: se o orçamento estiver definido como 0, considere que o cliente não informou o valor e não penalize o score)
        3. Fit de Experiência: O desafio condiz com a senioridade dele?
        4. Fit Cultural/Potencial: Leia a biografia do desenvolvedor (caso exista) e busque habilidades, experiências ou características que possam aproximá-lo da vaga
        
        Responda EXCLUSIVAMENTE com um JSON válido seguindo este formato rigoroso:
        {{
            "SCORE": 85,
            "EXPLICACAO": "Seu parecer analítico, curto e direto (em português), explicando por que deu esta nota e se vale a pena ele aplicar ou ignorar."
        }}
        """

        active_llm = _get_active_llm(user_id)
        dados_ia = generate_json(prompt, provedor=active_llm)

        novo_score = dados_ia.get("SCORE", 0)
        nova_explicacao = dados_ia.get("EXPLICACAO", "Análise não retornou justificativa.")

        # 4. Atualizar no Banco de Dados
        opp_repo.update_opportunity(vaga_id, {
            "score": novo_score,
            "explicacao_score": nova_explicacao,
            "status": "Analisada"
        })

        return {
            "mensagem": "Analista IA processou a vaga com sucesso!",
            "score": novo_score,
            "explicacao": nova_explicacao
        }

class RedatorService:
    @staticmethod
    def _get_tone_prompt(modelo_ativo: str, personalizado_prompt: str) -> str:
        if modelo_ativo == "consultivo":
            return "Adote um tom consultivo e estratégico. Foque em fazer perguntas pertinentes, mostrar que você entende o problema de negócio por trás da vaga e sugerir caminhos antes mesmo de falar de preço. Seja cordial, demonstrando muita autoridade no assunto."
        elif modelo_ativo == "direto":
            return "Adote um tom direto ao ponto, curto e extremamente objetivo. Profissionais que valorizam o tempo do cliente. Sem enrolação. Diga o que vai ser entregue, como vai ser entregue e por que você é a pessoa certa em poucas linhas."
        elif modelo_ativo == "personalizado" and personalizado_prompt:
            return f"Siga ESTRITAMENTE as seguintes diretrizes de estilo de escrita fornecidas pelo usuário:\n\n{personalizado_prompt}"
        else:
            return "Adote um tom profissional, amigável e equilibrado. Destaque a experiência relevante, aborde os pontos principais da vaga e termine com um convite aberto (call-to-action) para uma conversa."

    @staticmethod
    def gerar_proposta(vaga_id: str, user_id: str) -> dict:
        vaga = opp_repo.get_opportunity(vaga_id)
        if not vaga:
            raise ValueError("Oportunidade não encontrada.")
            
        perfil = profile_repo.get_profile(user_id)
        if not perfil:
            raise ValueError("Perfil não encontrado.")

        conf_user = profile_repo.get_user_settings(user_id)
        modelo_ativo = "padrao"
        personalizado_prompt = ""
        github_resumo = ""

        if conf_user:
            github_resumo = conf_user.get("github_resumo", "")
            if conf_user.get("modelos_proposta"):
                mod = conf_user["modelos_proposta"]
            if isinstance(mod, dict):
                modelo_ativo = mod.get("ativo", "padrao")
                personalizado_prompt = mod.get("personalizado_prompt", "")

        tone_instructions = RedatorService._get_tone_prompt(modelo_ativo, personalizado_prompt)

        sys_prompt = f"""Você é o Redator IA, um especialista em vendas B2B e captação de clientes que buscam freelancers.
Sua missão é escrever uma proposta matadora para a vaga descrita abaixo, se passando pelo perfil do profissional.

[PERFIL DO PROFISSIONAL]
Nome/Identificação: {perfil.get('nome', 'Profissional')}
Bio/Resumo: {perfil.get('bio', 'Não informado')}
Habilidades: {', '.join(perfil.get('habilidades', []))}
Nível de Experiência: {perfil.get('senioridade', 'Não informado')}
{f'Análise do Portfólio (GitHub): {github_resumo}' if github_resumo else ''}

[DADOS DA VAGA]
Título: {vaga.get('titulo')}
Nome do cliente: {vaga.get('cliente', '').split(' ')[0] if vaga.get('cliente') else ''}
Descrição Completa: {vaga.get('descricao')}
Orçamento: R$ {vaga.get('orcamento')}

[ESTILO DA PROPOSTA (DIRETRIZ OBRIGATÓRIA)]
{tone_instructions}

[INSTRUÇÕES GERAIS]
1. A proposta deve ser formatada em texto claro, com parágrafos curtos.
2. Seja persuasivo, mas honesto. Não invente habilidades que não estão no perfil do profissional.
3. Se houver correspondência entre a stack exigida na vaga e os projetos mencionados na Análise do Portfólio (GitHub) (se não existir, desconsidere essa instrução), você DEVE citar explicitamente o nome desses projetos
(substitua caracteres de separação '-', '_', '.' por espaços ' '; formate o nome dos projetos em TITLE CASE) e um breve resumo deles na proposta para gerar autoridade imediata.
4. Escreva em Português do Brasil de forma natural (evite clichês de IA).
5. No começo de toda proposta inicie com "Olá, 'nome do cliente'! Tudo bem?" (substitua 'nome do cliente' pelo nome real do cliente, se disponível; caso contrário, use "Olá! ...").
6. Assine no final com o nome do profissional.
7. Estime o "valor" (apenas números inteiros) e o "prazo" (ex: "7 dias", "1 mês") ideais para a vaga.
8. Não esqueça de incluir quebras de linha entre parágrafos.
9. RETORNE UM JSON VÁLIDO COM A SEGUINTE ESTRUTURA (EXEMPLO) E NADA MAIS (sem formatação markdown ```json):
{{
  "texto_proposta": "Olá 'nome do cliente'! Tudo bem? (quebra de linha) Me chamo `APENAS O PRIMEIRO nome do desenvolvedor´, sou desenvolvedor... [...] -Termine o texto com:- Atenciosamente, APENAS O PRIMEIRO nome do desenvolvedor´",
  "valor": 1500,
  "prazo": "7 dias"
}}
"""
        active_llm = _get_active_llm(user_id)                   ## para o redator modelos especificios se mostraram mais eficientes - TESTES SENDO REALIZADOS
        dados_ia = generate_json(sys_prompt, provedor="openrouter", force_json=True)
        
        texto_proposta = dados_ia.get("texto_proposta", "") 
        valor_proposta = dados_ia.get("valor", 0)
        prazo_proposta = dados_ia.get("prazo", "")
        
        opp_repo.update_opportunity(vaga_id, {
            "proposta_ia": texto_proposta,
            "valor_proposta": valor_proposta,
            "prazo_proposta": prazo_proposta
        })
        
        return {
            "proposta": texto_proposta, 
            "valor": valor_proposta, 
            "prazo": prazo_proposta, 
            "modelo_utilizado": modelo_ativo
        }

class ScoutService:
    @staticmethod
    def analisar_vaga(texto: str, plataforma: str, perfil_id: str, foto_url: str = None) -> dict:
        prompt = f"""
        Você é o Scout IA, um agente especializado em analisar descrições de vagas para freelancers.
        Leia o texto abaixo e extraia as seguintes informações em formato JSON válido e rigoroso.
        Não adicione NENHUM texto extra ou formatação markdown, retorne APENAS as chaves abaixo:
        
        {{
          "TITULO": "Título resumido do projeto",
          "CLIENTE": "Nome do cliente ou 'Confidencial'",
          "ORCAMENTO": 0,
          "PRAZO": "ex: 2 semanas, indeterminado",
          "STACK": ["Tech1", "Tech2"],
          "DESCRICAO": "Resumo do que precisa ser feito. Seja conciso, mas completo. Evite repetir o título. Não inclua informações irrelevantes. Inclua apenas informações pertinentes à realização do projeto e a exigências do cliente, como stack/tecnologias necessárias, requisitos, entregáveis etc."
        }}

        TEXTO DA VAGA BRUTA:
        {texto}
        """

        active_llm = _get_active_llm(perfil_id)
        dados_ia = generate_json(prompt, provedor=active_llm, force_json=True)

        cliente_nome = dados_ia.get("CLIENTE", "Confidencial")
        
        c = client_repo.get_client_by_name(perfil_id, cliente_nome)
        if c:
            cliente_id = c["id"]
            if foto_url and not c.get("foto_url"):
                client_repo.update_client(cliente_id, {"foto_url": foto_url})
        else:
            novo_c_payload = {
                "perfil_id": perfil_id,
                "nome": cliente_nome,
                "status": "Ativo"
            }
            if foto_url:
                novo_c_payload["foto_url"] = foto_url
            novo_c = client_repo.create_client(novo_c_payload)
            cliente_id = novo_c.data[0]["id"] if novo_c.data else None

        registro = {
            "titulo": dados_ia.get("TITULO", "Sem Título"),
            "cliente": cliente_nome,
            "cliente_id": cliente_id,
            "cliente_foto_url": foto_url,
            "orcamento": dados_ia.get("ORCAMENTO", 0),
            "prazo": dados_ia.get("PRAZO", "Não informado"),
            "stack": dados_ia.get("STACK", []),
            "score": 0, 
            "descricao": dados_ia.get("DESCRICAO", ""),
            "plataforma": plataforma,
            "status": "Aguardando Análise",
            "perfil_id": perfil_id
        }
        
        result = opp_repo.create_opportunity(registro)
        
        return {
            "mensagem": "Scout IA analisou e salvou a vaga com sucesso!", 
            "vaga_id": result.data[0]["id"] if result.data else None,
            "vaga_processada": registro
        }
