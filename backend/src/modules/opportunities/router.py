from fastapi import Depends
from backend.src.core.auth import get_current_user, verify_user_ownership
from fastapi import APIRouter, HTTPException
from backend.src.modules.opportunities.schemas import AvaliacaoRequest, RedatorRequest, VagaBruta, OpportunityUpdate
from backend.src.modules.opportunities.service import AnalistaService, RedatorService, ScoutService
from backend.src.modules.opportunities.repository import OpportunityRepository, ClientRepository, ProfileRepository
from backend.src.modules.opportunities.workana_crawler import WorkanaCrawler

repo = OpportunityRepository()

router = APIRouter()

@router.post("/api/analista/evaluate")
def avaliar_oportunidade(req: AvaliacaoRequest, current_user: dict = Depends(get_current_user)):
    try:
        if hasattr(req, 'perfil_id') and getattr(req, 'perfil_id') != current_user['user_id']:
            raise HTTPException(status_code=403, detail="Acesso negado")
        resultado = AnalistaService.avaliar_oportunidade(req.vaga_id, req.user_id)
        return resultado
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro interno do Analista: {str(e)}")

@router.post("/api/redator/draft")
def gerar_proposta(req: RedatorRequest, current_user: dict = Depends(get_current_user)):
    try:
        if hasattr(req, 'perfil_id') and getattr(req, 'perfil_id') != current_user['user_id']:
            raise HTTPException(status_code=403, detail="Acesso negado")
        resultado = RedatorService.gerar_proposta(req.vaga_id, req.user_id)
        return resultado
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro interno do Redator: {str(e)}")

@router.post("/api/scout/analyze")
def analisar_vaga(vaga: VagaBruta, current_user: dict = Depends(get_current_user)):
    try:
        if hasattr(vaga, 'user_id') and getattr(vaga, 'user_id') != current_user['user_id']:
            raise HTTPException(status_code=403, detail="Acesso negado")
        if hasattr(vaga, 'perfil_id') and getattr(vaga, 'perfil_id') != current_user['user_id']:
            raise HTTPException(status_code=403, detail="Acesso negado")
        resultado = ScoutService.analisar_vaga(vaga.texto, vaga.plataforma, vaga.perfil_id, foto_url=vaga.foto_url)
        return resultado
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro interno do Scout: {str(e)}")

@router.post("/api/crawler/workana")
def rodar_crawler_workana(user_id: str, limit: int = 3, current_user: dict = Depends(get_current_user)):
    if user_id != current_user['user_id']: raise HTTPException(status_code=403, detail="Acesso negado")
    try:
        resultados = WorkanaCrawler.executar(user_id, limit)
        return {"status": "success", "extraidas": len(resultados), "resultados": resultados}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro no crawler: {str(e)}")

@router.get("/api/opportunities")
def list_opportunities(user_id: str, current_user: dict = Depends(get_current_user)):
    if user_id != current_user['user_id']: raise HTTPException(status_code=403, detail="Acesso negado")
    try:
        return repo.get_opportunities(user_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/opportunities/{vaga_id}")
def get_opportunity(vaga_id: str, current_user: dict = Depends(get_current_user)):
    try:
        res = repo.get_opportunity(vaga_id)
        if not res:
            raise HTTPException(status_code=404, detail="Vaga não encontrada")
        if res.get("perfil_id") != current_user['user_id']:
            raise HTTPException(status_code=403, detail="Acesso negado")
        return res
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/api/opportunities/{vaga_id}")
def update_opportunity(vaga_id: str, req: OpportunityUpdate, current_user: dict = Depends(get_current_user)):
    try:
        res_check = repo.get_opportunity(vaga_id)
        if res_check and res_check.get("perfil_id") != current_user['user_id']:
            raise HTTPException(status_code=403, detail="Acesso negado")
        data = req.model_dump(exclude_unset=True)
        res = repo.update_opportunity(vaga_id, data)
        return res
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/api/opportunities/delete_all")
def delete_all_opportunities(user_id: str, current_user: dict = Depends(get_current_user)):
    if user_id != current_user['user_id']: raise HTTPException(status_code=403, detail="Acesso negado")
    try:
        repo.delete_all_opportunities(user_id)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/api/opportunities/{vaga_id}")
def delete_opportunity(vaga_id: str, current_user: dict = Depends(get_current_user)):
    try:
        res_check = repo.get_opportunity(vaga_id)
        if res_check and res_check.get("perfil_id") != current_user['user_id']:
            raise HTTPException(status_code=403, detail="Acesso negado")
        repo.delete_opportunity(vaga_id)
        return {"status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/clients")
def list_clients(perfil_id: str, current_user: dict = Depends(get_current_user)):
    if perfil_id != current_user['user_id']: raise HTTPException(status_code=403, detail="Acesso negado")
    try:
        return ClientRepository().get_clients(perfil_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/profile")
def get_profile(user_id: str, current_user: dict = Depends(get_current_user)):
    if user_id != current_user['user_id']: raise HTTPException(status_code=403, detail="Acesso negado")
    try:
        profile = ProfileRepository().get_profile(user_id)
        if not profile:
            raise HTTPException(status_code=404, detail="Perfil não encontrado")
        return profile
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
@router.delete("/api/clients/inactive")
def delete_inactive_clients(perfil_id: str, current_user: dict = Depends(get_current_user)):
    if perfil_id != current_user['user_id']: raise HTTPException(status_code=403, detail="Acesso negado")
    try:
        ClientRepository().delete_inactive_clients(perfil_id)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
