from sqlalchemy import Table, Column, Integer, String, ForeignKey, DateTime, Boolean, Float, Index
from sqlalchemy.orm import relationship
from datetime import datetime
from data.database import Base

# 1. TABLE D'ASSOCIATION (Doit être définie avant son utilisation)
association_objet_fonction = Table(
    "association_objet_fonction",
    Base.metadata,
    Column("id_objet", Integer, ForeignKey("objets.id_objet"), primary_key=True),
    Column("id_fonction", Integer, ForeignKey("fonctionnalites.id"), primary_key=True)
)

class Etage(Base):
    __tablename__ = "etages"
    num_etage = Column(Integer, primary_key=True, index=True)
    nom_building = Column(String)
    hauteur_metres = Column(Float)
    plan_2d_url = Column(String, nullable=True)
    
    salles = relationship("Salle", back_populates="etage")

class Salle(Base):
    __tablename__ = "salles"
    id_salle = Column(Integer, primary_key=True, index=True)
    nom_salle = Column(String)
    coord_x = Column(Float) # Position X du bord supérieur gauche
    coord_y = Column(Float) # Position Y du bord supérieur gauche
    largeur = Column(Float, default=20.0) # Largeur de la salle (en pourcentage ou mètres)
    longueur = Column(Float, default=20.0) # Hauteur de la salle
    num_etage = Column(Integer, ForeignKey("etages.num_etage"), index=True) # Index jointure
    
    etage = relationship("Etage", back_populates="salles")
    objets = relationship("Objet", back_populates="salle")

class Fonctionnalite(Base):
    __tablename__ = "fonctionnalites"
    id = Column(Integer, primary_key=True, index=True)
    nom = Column(String, unique=True, index=True)
    
    objets = relationship("Objet", secondary=association_objet_fonction, back_populates="fonctionnalites")


class Alerte(Base):
    __tablename__ = "alertes"
    
    id_alerte = Column(Integer, primary_key=True, index=True)
    message = Column(String) # Ex: "Bourrage papier", "Surchauffe"
    niveau = Column(String, default="Warning") # Info, Warning, Critical
    source = Column(String) # "Utilisateur" ou "IoT"
    date_alerte = Column(DateTime, default=datetime.utcnow)
    est_resolu = Column(Boolean, default=False) # True quand l'admin a traité le problème

    # Clés étrangères
    id_objet = Column(Integer, ForeignKey("objets.id_objet"), index=True)
    id_utilisateur = Column(Integer, ForeignKey("utilisateurs.id_utilisateur"), nullable=True) # Null si c'est l'IoT
    
    objet = relationship("Objet", back_populates="alertes")


class Objet(Base):
    __tablename__ = "objets"
    id_objet = Column(Integer, primary_key=True, index=True)
    nom_model = Column(String, index=True)
    nom_marque = Column(String, index=True)
    type_objet = Column(String, index=True)
    description = Column(String, nullable=True)
    # IoT & Réseau
    mac_adresse = Column(String, unique=True, index=True)
    ip_adress = Column(String, nullable=True)
    pos_x = Column(Float, nullable=True)
    pos_y = Column(Float, nullable=True)
    statut = Column(String, default="Disponible", index=True) # Disponible, Occupé, Panne
    last_heartbeat = Column(DateTime, default=datetime.utcnow)
    
    url_photo = Column(String, nullable=True)
    
    # Clé étrangère indexée pour la performance
    id_salle = Column(Integer, ForeignKey("salles.id_salle"), index=True)

    salle = relationship("Salle", back_populates="objets")
    reservations = relationship("Reservation", back_populates="objet")
    fonctionnalites = relationship("Fonctionnalite", secondary=association_objet_fonction, back_populates="objets")
    alertes = relationship("Alerte", back_populates="objet")
    
    # OPTIMISATION MAJEURE : Index Composite pour la recherche Full-Text
    __table_args__ = (
        Index(
            'idx_objets_full_search',
            'nom_model', 'type_objet', 'nom_marque',
            postgresql_ops={
                'nom_model': 'gin_trgm_ops',
                'type_objet': 'gin_trgm_ops',
                'nom_marque': 'gin_trgm_ops'
            },
            postgresql_using='gin'
        ),
    )

class Utilisateur(Base):
    __tablename__ = "utilisateurs"
    id_utilisateur = Column(Integer, primary_key=True, index=True)
    nom = Column(String)
    prenom = Column(String)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    role = Column(String, default="Utilisateur") # "Utilisateur" ou "Admin"
    est_verifie = Column(Boolean, default=False)
    code_verification = Column(String, nullable=True)

    reservations = relationship("Reservation", back_populates="utilisateur")
    historiques = relationship("Historique", back_populates="utilisateur")
    notifications = relationship("Notification", back_populates="utilisateur")

class Reservation(Base):
    __tablename__ = "reservations"
    id = Column(Integer, primary_key=True, index=True)
    id_utilisateur = Column(Integer, ForeignKey("utilisateurs.id_utilisateur"), index=True)
    id_objet = Column(Integer, ForeignKey("objets.id_objet"), index=True)
    date_reservation = Column(DateTime, default=datetime.utcnow)
    statut_reservation = Column(String, default="Active")

    utilisateur = relationship("Utilisateur", back_populates="reservations")
    objet = relationship("Objet", back_populates="reservations")

class Historique(Base):
    __tablename__ = "historiques"
    id_historique = Column(Integer, primary_key=True, index=True)
    date_his = Column(DateTime, default=datetime.utcnow)
    requete_search = Column(String)
    id_utilisateur = Column(Integer, ForeignKey("utilisateurs.id_utilisateur"), index=True)
    
    utilisateur = relationship("Utilisateur", back_populates="historiques")


class Notification(Base):
    __tablename__ = "notifications"
    id_notification = Column(Integer, primary_key=True, index=True)
    message = Column(String, nullable=False)
    type_notification = Column(String, default="INFO")
    est_lu = Column(Boolean, default=False, index=True)
    date_notification = Column(DateTime, default=datetime.utcnow, index=True)

    id_utilisateur = Column(Integer, ForeignKey("utilisateurs.id_utilisateur"), index=True)
    id_objet = Column(Integer, ForeignKey("objets.id_objet"), nullable=True, index=True)
    id_reservation = Column(Integer, ForeignKey("reservations.id"), nullable=True, index=True)

    utilisateur = relationship("Utilisateur", back_populates="notifications")


