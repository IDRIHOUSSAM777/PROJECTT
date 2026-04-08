import asyncio
import subprocess
import platform

async def check_ip_active(ip_adress: str) -> bool:
    """
    Ping une adresse IP de manière asynchrone pour vérifier si l'appareil est actif.
    Retourne True si un ping a réussi, False sinon.
    """
    if not ip_adress:
        return False
        
    ip_adress = ip_adress.strip()
    
    # Paramètre pour ne tester qu'un seul ping (-n sous Windows, -c sous Linux/Mac)
    # Paramètre pour un délai d'attente max (-w sous Windows, -W sous Linux/Mac)
    param = '-n' if platform.system().lower() == 'windows' else '-c'
    timeout_param = '-w' if platform.system().lower() == 'windows' else '-W'
    
    # Commande ping: 1 essai (c 1), Attente max 1 seconde (W 1)
    command = ['ping', param, '1', timeout_param, '1', ip_adress]
    
    try:
        # Exécution asynchrone pour ne pas bloquer le serveur FastAPI
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        
        # Attendre que la commande se termine
        await process.wait()
        
        # Code de retour 0 = Succès (Ping a répondu)
        return process.returncode == 0
        
    except Exception as e:
        print(f"Erreur de ping pour l'IP {ip_adress}: {str(e)}")
        return False
