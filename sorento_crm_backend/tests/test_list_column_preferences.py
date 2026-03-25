import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from app.database import Base
from app.dependencies import get_current_user, get_db
from app.main import app
from app.models.user import (
    User,
    UserPermission,
    UserRole,
    UserRoleAssignment,
    UserRolePermission,
    UserListColumnConfig,
)


def _seed_rbac_and_user(db: Session, *, user_id: str, permission_slug: str, role_id: str = 'r1') -> None:
    existing_perm = db.query(UserPermission).filter(UserPermission.slug == permission_slug).first()
    if existing_perm is None:
        perm = UserPermission(
            id=f'perm_{permission_slug}',
            slug=permission_slug,
            name='Test perm',
            description='',
        )
        db.add(perm)
        db.flush()
    else:
        perm = existing_perm

    existing_role = db.query(UserRole).filter(UserRole.id == role_id).first()
    if existing_role is None:
        role = UserRole(
            id=role_id,
            slug=f'role_{role_id}',
            name=f'Role {role_id}',
            description='',
            is_trashed=False,
            is_protected=False,
            is_default=False,
        )
        db.add(role)
        db.flush()
    else:
        role = existing_role

    if (
        db.query(UserRolePermission)
        .filter(UserRolePermission.role_id == role.id, UserRolePermission.permission_id == perm.id)
        .first()
        is None
    ):
        db.add(UserRolePermission(role_id=role.id, permission_id=perm.id))

    existing_user = db.query(User).filter(User.id == user_id).first()
    if existing_user is None:
        user = User(id=user_id, email=f'{user_id}@test.com', status='ACTIVE', name='User')
        db.add(user)
        db.flush()
    else:
        user = existing_user

    if (
        db.query(UserRoleAssignment)
        .filter(UserRoleAssignment.user_id == user.id, UserRoleAssignment.role_id == role.id)
        .first()
        is None
    ):
        db.add(UserRoleAssignment(user_id=user.id, role_id=role.id))

    db.commit()


@pytest.fixture
def api_client():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()

    current_user = {'id': 'u1'}

    def _override_current_user():
        return {'id': current_user['id']}

    def _override_get_db():
        yield db

    app.dependency_overrides[get_current_user] = _override_current_user
    app.dependency_overrides[get_db] = _override_get_db

    with TestClient(app) as client:
        yield client, current_user, db

    app.dependency_overrides.clear()
    db.close()


def test_list_column_config_upsert_and_reset(api_client):
    client, current_user, db = api_client

    perm_slug = 'test.orders.view'
    _seed_rbac_and_user(db, user_id='u1', permission_slug=perm_slug, role_id='r1')

    listing_key = f'{perm_slug}::orders-list'

    r0 = client.get(f'/api/v1/list-query/column-config/{listing_key}')
    assert r0.status_code == 200
    assert r0.json()['listing_key'] == listing_key
    assert r0.json()['config'] is None

    payload = {
        'version': 1,
        'columnOrder': ['name', 'status'],
        'columnVisibility': { 'name': True, 'status': False },
    }
    r1 = client.put(f'/api/v1/list-query/column-config/{listing_key}', json=payload)
    assert r1.status_code == 200
    assert r1.json()['config']['columnOrder'] == payload['columnOrder']

    r2 = client.get(f'/api/v1/list-query/column-config/{listing_key}')
    assert r2.status_code == 200
    assert r2.json()['config']['columnVisibility']['status'] is False

    # Reset
    r3 = client.delete(f'/api/v1/list-query/column-config/{listing_key}')
    assert r3.status_code == 204

    r4 = client.get(f'/api/v1/list-query/column-config/{listing_key}')
    assert r4.status_code == 200
    assert r4.json()['config'] is None


def test_list_column_config_denied_without_permission(api_client):
    client, _, db = api_client

    # User has perm A, tries perm B (permission B exists but is not granted).
    _seed_rbac_and_user(db, user_id='u1', permission_slug='test.a.view', role_id='r1')
    db.add(UserPermission(id='perm_test.b.view', slug='test.b.view', name='Test perm', description=''))
    db.commit()

    listing_key = 'test.b.view::b-list'
    r = client.get(f'/api/v1/list-query/column-config/{listing_key}')
    assert r.status_code == 403


def test_list_column_config_per_user_isolation(api_client):
    client, current_user, db = api_client

    perm_slug = 'test.products.view'
    _seed_rbac_and_user(db, user_id='u1', permission_slug=perm_slug, role_id='r1')
    _seed_rbac_and_user(db, user_id='u2', permission_slug=perm_slug, role_id='r2')

    listing_key = f'{perm_slug}::products-list'

    payload = {
        'version': 1,
        'columnOrder': ['code'],
        'columnVisibility': { 'code': True },
    }

    current_user['id'] = 'u1'
    r1 = client.put(f'/api/v1/list-query/column-config/{listing_key}', json=payload)
    assert r1.status_code == 200

    current_user['id'] = 'u2'
    r2 = client.get(f'/api/v1/list-query/column-config/{listing_key}')
    assert r2.status_code == 200
    assert r2.json()['config'] is None


def test_list_column_config_allows_when_permission_slug_unknown(api_client):
    client, current_user, db = api_client

    # Ensure we have a user row; the permission slug won't exist in RBAC catalog.
    user = User(id='u1', email='u1@test.com', status='ACTIVE', name='User')
    db.add(user)
    db.commit()

    current_user['id'] = 'u1'
    listing_key = 'nonexistent.permission.slug::x'

    r = client.get(f'/api/v1/list-query/column-config/{listing_key}')
    assert r.status_code == 200
    assert r.json()['config'] is None

