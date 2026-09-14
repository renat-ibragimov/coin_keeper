import { useMutation } from '@tanstack/react-query';
import { User } from 'lucide-react';
import { useRef, useState } from 'react';
import type { ChangeEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { useAuth } from '@/features/auth/useAuth';
import { ApiError } from '@/shared/api/client';
import { Button, useToast } from '@/shared/ui';

import { deleteAvatar, uploadAvatar } from './api';
import { AvatarCropDialog } from './AvatarCropDialog';
import styles from './AvatarSection.module.css';

const ACCEPTED = 'image/jpeg,image/png,image/webp';

/** The profile picture: pick a file, frame the circle, upload or clear it. */
export function AvatarSection() {
  const { t } = useTranslation();
  const { user, updateUser } = useAuth();
  const toast = useToast();
  const fileInput = useRef<HTMLInputElement>(null);
  const [picked, setPicked] = useState<string | null>(null);

  /** Object URLs are held by the document until released by hand. */
  function releasePicked() {
    setPicked((current) => {
      if (current) URL.revokeObjectURL(current);
      return null;
    });
  }

  const uploadMutation = useMutation({
    mutationFn: (image: Blob) => uploadAvatar(image),
    onSuccess: (updated) => {
      releasePicked();
      updateUser(updated);
      toast.show(t('settings.avatarSaved'));
    },
    onError: (error) => {
      releasePicked();
      const rejected = error instanceof ApiError && error.problemType === 'invalid-image';
      toast.show(rejected ? t('settings.avatarInvalid') : t('errors.generic'));
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteAvatar,
    onSuccess: (updated) => {
      updateUser(updated);
      toast.show(t('settings.avatarRemoved'));
    },
    onError: () => toast.show(t('errors.generic')),
  });

  function pickFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    // Clearing the input is what lets the same file be picked twice: without
    // it the second pick is not a change and fires nothing.
    event.target.value = '';
    if (!file) return;
    if (!ACCEPTED.split(',').includes(file.type)) {
      toast.show(t('settings.avatarInvalid'));
      return;
    }
    releasePicked();
    setPicked(URL.createObjectURL(file));
  }

  const hasAvatar = Boolean(user?.avatarUrl);

  return (
    <div className={styles.section}>
      <span className={styles.preview}>
        {user?.avatarUrl ? (
          <img className={styles.image} src={user.avatarUrl} alt="" />
        ) : (
          <User size={30} aria-hidden="true" />
        )}
      </span>

      <div className={styles.controls}>
        <div className={styles.buttons}>
          <Button variant="secondary" onClick={() => fileInput.current?.click()}>
            {hasAvatar ? t('settings.avatarChange') : t('settings.avatarUpload')}
          </Button>
          {hasAvatar ? (
            <Button
              variant="ghost"
              loading={deleteMutation.isPending}
              onClick={() => deleteMutation.mutate()}
            >
              {t('common.delete')}
            </Button>
          ) : null}
        </div>
        <p className={styles.hint}>{t('settings.avatarHint')}</p>
      </div>

      <input
        ref={fileInput}
        type="file"
        accept={ACCEPTED}
        className={styles.fileInput}
        onChange={pickFile}
      />

      {/* Keyed on the picked file: a second photo opens on a fresh circle
          rather than inheriting the zoom and offset of the previous one. */}
      <AvatarCropDialog
        key={picked ?? 'none'}
        image={picked}
        busy={uploadMutation.isPending}
        onCancel={releasePicked}
        onSave={(cropped) => uploadMutation.mutate(cropped)}
      />
    </div>
  );
}
