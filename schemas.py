import re
from pydantic import BaseModel, Field, field_validator
from core.nostr import convert_npub_to_hex


class ValidatedUsernameMixin:
    @field_validator('username')
    @classmethod
    def validate_username(cls, v: str) -> str:
        if not re.match(r'^[a-zA-Z0-9_-]{1,30}$', v):
            raise ValueError(
                'Username must be 1-30 characters, letters, numbers, underscores or hyphens only'
            )
        return v


class ValidatedPubkeyMixin:
    @field_validator('pubkey')
    @classmethod
    def validate_pubkey(cls, v: str) -> str:
        try:
            convert_npub_to_hex(v)
        except ValueError as e:
            raise ValueError(str(e))
        return v


class ValidatedDomainMixin:
    @field_validator('domain')
    @classmethod
    def validate_domain(cls, v: str) -> str:
        from config import DOMAINS_MAP, PRIMARY_DOMAIN
        if not v:
            return PRIMARY_DOMAIN
        if v not in DOMAINS_MAP:
            raise ValueError(f'Domain not configured: {v}')
        return v


class NIP05Request(ValidatedUsernameMixin, ValidatedPubkeyMixin, ValidatedDomainMixin, BaseModel):
    username: str = Field(max_length=30)
    pubkey: str = Field(max_length=200)
    domain: str = Field(default="", max_length=253)


class ConvertPubkeyRequest(ValidatedPubkeyMixin, BaseModel):
    pubkey: str = Field(max_length=200)


class CheckPubkeyRequest(ValidatedPubkeyMixin, ValidatedDomainMixin, BaseModel):
    pubkey: str = Field(max_length=200)
    domain: str = Field(default="", max_length=253)


class CheckPaymentRequest(ValidatedPubkeyMixin, ValidatedUsernameMixin, ValidatedDomainMixin, BaseModel):
    username: str = Field(max_length=30)
    pubkey: str = Field(max_length=200)
    payment_hash: str = Field(max_length=64)
    domain: str = Field(default="", max_length=253)

    @field_validator('payment_hash')
    @classmethod
    def validate_payment_hash(cls, v: str) -> str:
        if not re.match(r'^[a-fA-F0-9]{64}$', v):
            raise ValueError('Invalid payment hash format')
        return v


class CancelRegistrationRequest(ValidatedDomainMixin, BaseModel):
    username: str = Field(max_length=50)
    domain: str = Field(default="", max_length=253)


class LoginRequest(BaseModel):
    username: str = Field(max_length=50)
    password: str = Field(max_length=200)


class ManageRecordRequest(BaseModel):
    nip05: str = Field(max_length=100)
    pubkey: str = Field(max_length=200)
    id: int | None = None


class PasswordResetRequest(BaseModel):
    username: str = Field(max_length=50)


class PasswordResetConfirm(BaseModel):
    token: str = Field(max_length=100)
    new_password: str = Field(min_length=8, max_length=200)


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(min_length=8, max_length=200)
    new_password: str = Field(min_length=8, max_length=200)


class ProfileUpdateRequest(BaseModel):
    email: str | None = None


class UserCreateRequest(BaseModel):
    username: str = Field(max_length=50)
    password: str = Field(min_length=8, max_length=200)
    email: str | None = None
    role: str = Field(max_length=20)


class UserUpdateRequest(BaseModel):
    id: int
    email: str | None = None
    role: str = Field(max_length=20)
    is_active: bool


class UserResetPasswordRequest(BaseModel):
    user_id: int
    new_password: str = Field(min_length=8, max_length=200)
