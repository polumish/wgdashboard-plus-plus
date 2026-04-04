import datetime
import uuid

from .ConnectionString import ConnectionString
from .DashboardLogger import DashboardLogger
import sqlalchemy as db
from .WireguardConfiguration import WireguardConfiguration


class ConfigAccess:
    def __init__(self, **kwargs):
        self.AccessID: str = kwargs.get('AccessID')
        self.ClientID: str = kwargs.get('ClientID')
        self.ConfigurationName: str = kwargs.get('ConfigurationName')
        self.Role: str = kwargs.get('Role', 'viewer')
        self.GrantedDate: datetime.datetime = kwargs.get('GrantedDate')
        self.RevokedDate: datetime.datetime = kwargs.get('RevokedDate')

    def toJson(self):
        return {
            "AccessID": self.AccessID,
            "ClientID": self.ClientID,
            "ConfigurationName": self.ConfigurationName,
            "Role": self.Role,
            "GrantedDate": self.GrantedDate.strftime("%Y-%m-%d %H:%M:%S"),
            "RevokedDate": self.RevokedDate.strftime("%Y-%m-%d %H:%M:%S") if self.RevokedDate else None
        }


class DashboardClientConfigAccess:
    def __init__(self, wireguardConfigurations: dict[str, WireguardConfiguration]):
        self.logger = DashboardLogger()
        self.engine = db.create_engine(ConnectionString("wgdashboard"))
        self.metadata = db.MetaData()
        self.wireguardConfigurations = wireguardConfigurations
        self.table = db.Table(
            'DashboardClientConfigAccess', self.metadata,
            db.Column('AccessID', db.String(255), nullable=False, primary_key=True),
            db.Column('ClientID', db.String(255), nullable=False, index=True),
            db.Column('ConfigurationName', db.String(255), nullable=False),
            db.Column('Role', db.String(50), nullable=False, server_default='viewer'),
            db.Column('GrantedDate',
                      (db.DATETIME if 'sqlite:///' in ConnectionString("wgdashboard") else db.TIMESTAMP),
                      server_default=db.func.now()),
            db.Column('RevokedDate',
                      (db.DATETIME if 'sqlite:///' in ConnectionString("wgdashboard") else db.TIMESTAMP)),
            extend_existing=True
        )
        self.metadata.create_all(self.engine)
        self.accesses: list[ConfigAccess] = []
        self.__loadAccesses()

    def __loadAccesses(self):
        with self.engine.connect() as conn:
            rows = conn.execute(
                self.table.select().where(self.table.c.RevokedDate.is_(None))
            ).mappings().fetchall()
            self.accesses = [ConfigAccess(**r) for r in rows]

    def GrantAccess(self, ClientID: str, ConfigurationName: str, Role: str = 'manager') -> tuple[bool, dict | None]:
        if ConfigurationName not in self.wireguardConfigurations:
            return False, None
        if Role not in ('viewer', 'manager'):
            return False, None
        existing = [a for a in self.accesses
                    if a.ClientID == ClientID and a.ConfigurationName == ConfigurationName]
        if existing:
            return False, None
        data = {
            "AccessID": str(uuid.uuid4()),
            "ClientID": ClientID,
            "ConfigurationName": ConfigurationName,
            "Role": Role,
        }
        with self.engine.begin() as conn:
            conn.execute(self.table.insert().values(data))
        self.__loadAccesses()
        return True, data

    def RevokeAccess(self, AccessID: str) -> bool:
        existing = [a for a in self.accesses if a.AccessID == AccessID]
        if not existing:
            return False
        with self.engine.begin() as conn:
            conn.execute(
                self.table.update().values({"RevokedDate": datetime.datetime.now()})
                .where(self.table.c.AccessID == AccessID)
            )
        self.__loadAccesses()
        return True

    def GetClientConfigurations(self, ClientID: str) -> list[dict]:
        self.__loadAccesses()
        return [a.toJson() for a in self.accesses if a.ClientID == ClientID]

    def GetClientManagedConfigurations(self, ClientID: str) -> list[str]:
        self.__loadAccesses()
        return [a.ConfigurationName for a in self.accesses
                if a.ClientID == ClientID and a.Role == 'manager']

    def HasAccess(self, ClientID: str, ConfigurationName: str, RequiredRole: str = 'viewer') -> bool:
        self.__loadAccesses()
        for a in self.accesses:
            if a.ClientID == ClientID and a.ConfigurationName == ConfigurationName:
                if RequiredRole == 'viewer':
                    return True
                if RequiredRole == 'manager' and a.Role == 'manager':
                    return True
        return False
