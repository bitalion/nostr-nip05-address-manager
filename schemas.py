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


class NIP05Request(ValidatedUsernameMixin, ValidatedPubkeyMixin, BaseModel):
    username: str = Field(max_length=30)
    pubkey: str = Field(max_length=200)


class ConvertPubkeyRequest(ValidatedPubkeyMixin, BaseModel):
    pubkey: str = Field(max_length=200)


class CheckPaymentRequest(ValidatedPubkeyMixin, ValidatedUsernameMixin, BaseModel):
    username: str = Field(max_length=30)
    pubkey: str = Field(max_length=200)
    payment_hash: str = Field(max_length=64)

    @field_validator('payment_hash')
    @classmethod
    def validate_payment_hash(cls, v: str) -> str:
        if not re.match(r'^[a-fA-F0-9]{64}$', v):
            raise ValueError('Invalid payment hash format')
        return v


class CancelRegistrationRequest(BaseModel):
    username: str = Field(max_length=50)


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
    new_password: str = Field(max_length=200)


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(max_length=200)
    new_password: str = Field(max_length=200)


class ProfileUpdateRequest(BaseModel):
    email: str | None = None


class UserCreateRequest(BaseModel):
    username: str = Field(max_length=50)
    password: str = Field(max_length=200)
    email: str | None = None
    role: str = Field(max_length=20)


class UserUpdateRequest(BaseModel):
    id: int
    email: str | None = None
    role: str = Field(max_length=20)
    is_active: bool


class UserResetPasswordRequest(BaseModel):
    user_id: int
    new_password: str = Field(max_length=200)
