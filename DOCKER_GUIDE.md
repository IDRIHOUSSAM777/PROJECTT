# SmartFind - Guide de Démarrage Rapide (Docker) 🐳

Bienvenue dans le projet SmartFind ! Pour faciliter le développement et l'exécution locale de notre plateforme, nous utilisons **Docker** et **Docker Compose**. Cela vous permet de lancer l'intégralité du projet (Base de données, Cache, Backend, et Frontend) avec une seule commande !

## 📋 Prérequis

Vous n'avez besoin que d'un seul outil installé sur votre machine :
1. **Docker Desktop** : [Télécharger et installer Docker](https://www.docker.com/products/docker-desktop/)
   (Assurez-vous que l'application Docker est ouverte et en cours d'exécution sur votre machine).

---

## 🚀 Comment Lancer le Projet

1. **Ouvrez votre terminal** et placez-vous à la racine du projet (là où se trouve le fichier `docker-compose.yml`).
2. **Exécutez la commande magique** :
   ```bash
   docker-compose up -d --build
   ```
   *L'argument `-d` permet de lancer les conteneurs en arrière-plan sans bloquer votre terminal. Le `--build` s'assure que vous prenez en compte les dernières modifications du code.*

3. **Patientez quelques secondes** le temps que l'installation initiale se termine (le Postgres et le Redis démarrent, les paquets Python s'installent, et React est compilé).

---

## 🌐 Accéder à l'Application

Une fois que les conteneurs tournent en vert sur votre Docker Desktop, accédez aux services localement :

- **Application Frontend (L'interface web)** : [http://localhost:80](http://localhost:80)
- **API Backend (FastAPI Documentation)** : [http://localhost:8000/docs](http://localhost:8000/docs)
- **Base de données (Postgres)** : Connectée automatiquement en coulisses sur le port `5432`.
- **Redis (Cache)** : Connecté automatiquement en coulisses sur le port `6379`.

---

## 🛠️ Commandes Utiles

- **Voir si tout fonctionne bien** :
  ```bash
  docker-compose ps
  ```
- **Lire les logs en temps réel (pratique pour le débug !)** :
  ```bash
  docker-compose logs -f
  ```
- **Arrêter proprement le projet** (sans effacer vos données) :
  ```bash
  docker-compose stop
  ```
- **Fermer complètement et supprimer les processus** :
  ```bash
  docker-compose down
  ```
*(Note : Rassurez-vous, la base de données est enregistrée de façon persistante dans un volume local. Vous ne perdrez pas vos informations en l'arrêtant !)*

Bon développement ! 🚀
