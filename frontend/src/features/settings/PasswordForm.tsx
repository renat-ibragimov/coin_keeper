import { useState } from 'react';
import type { FormEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { ApiError } from '@/shared/api/client';
import { PasswordInput } from '@/features/auth/pages/PasswordInput';
import { Button, FormActions, FormError, FormStack } from '@/shared/ui';

const MIN_LENGTH = 10;

interface PasswordFormProps {
  busy: boolean;
  submitError: unknown;
  /** Resolves when the server accepted the change; the form then clears. */
  onSubmit: (currentPassword: string, newPassword: string) => Promise<void>;
}

export function PasswordForm({ busy, submitError, onSubmit }: PasswordFormProps) {
  const { t } = useTranslation();
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [repeat, setRepeat] = useState('');
  const [errors, setErrors] = useState<{ next?: string; repeat?: string }>({});

  const serverError =
    submitError instanceof ApiError
      ? submitError.problemType === 'invalid-credentials'
        ? t('settings.wrongCurrentPassword')
        : submitError.problemType === 'weak-password'
          ? t('auth.weakPassword')
          : t('errors.generic')
      : submitError
        ? t('errors.generic')
        : null;

  async function submit(event: FormEvent) {
    event.preventDefault();
    const validation: typeof errors = {};
    if (next.length < MIN_LENGTH) validation.next = t('auth.weakPassword');
    if (repeat !== next) validation.repeat = t('auth.passwordsDontMatch');
    setErrors(validation);
    if (Object.keys(validation).length > 0) return;
    try {
      await onSubmit(current, next);
      setCurrent('');
      setNext('');
      setRepeat('');
    } catch {
      /* shown through submitError */
    }
  }

  return (
    <form onSubmit={(event) => void submit(event)} noValidate data-testid="password-form">
      <FormStack>
        <FormError>{serverError}</FormError>
        <PasswordInput
          label={t('settings.currentPassword')}
          // "current-password" is the semantically correct value, but Chrome
          // shows it a dropdown of unrelated remembered text (owner's report,
          // 2026-09-13) rather than an actual saved-password prompt here --
          // this form changes a password already known to be correct, not a
          // login, so there is nothing worth autofilling anyway.
          autoComplete="off"
          required
          value={current}
          onChange={(event) => setCurrent(event.target.value)}
        />
        <PasswordInput
          label={t('settings.newPassword')}
          autoComplete="off"
          required
          hint={t('auth.passwordHint')}
          value={next}
          onChange={(event) => {
            setNext(event.target.value);
            setErrors((error) => ({ ...error, next: undefined }));
          }}
          error={errors.next}
        />
        <PasswordInput
          label={t('auth.repeatPassword')}
          autoComplete="off"
          required
          value={repeat}
          onChange={(event) => {
            setRepeat(event.target.value);
            setErrors((error) => ({ ...error, repeat: undefined }));
          }}
          error={errors.repeat}
        />
        <FormActions>
          <Button type="submit" loading={busy}>
            {t('settings.changePassword')}
          </Button>
        </FormActions>
      </FormStack>
    </form>
  );
}
