import { useMutation, useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import type { FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import { useAuth } from '@/features/auth/useAuth';
import { fetchBootstrap } from '@/features/dashboard/api';
import { setLocale } from '@/shared/i18n';
import type { Locale } from '@/shared/i18n';
import { useTheme } from '@/shared/theme/useTheme';
import {
  Badge,
  Button,
  Card,
  FormActions,
  FormError,
  FormRow,
  FormStack,
  Input,
  PageHeader,
  PropertyList,
  Select,
  Tabs,
  useToast,
} from '@/shared/ui';

import { changePassword, updateProfile } from './api';
import { PasswordForm } from './PasswordForm';
import styles from './SettingsPage.module.css';

export function SettingsPage() {
  const { t, i18n } = useTranslation();
  const { user, updateUser, signOut } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const toast = useToast();

  const bootstrapQuery = useQuery({ queryKey: ['bootstrap'], queryFn: fetchBootstrap });
  const [displayName, setDisplayName] = useState(user?.displayName ?? '');
  const [locale, setLocaleField] = useState<Locale>(user?.locale === 'en' ? 'en' : 'uk');

  const profileMutation = useMutation({
    mutationFn: () => updateProfile({ displayName: displayName.trim() || null, locale }),
    onSuccess: (updated) => {
      updateUser(updated);
      setLocale(locale);
      toast.show(t('settings.profileSaved'));
    },
  });
  const passwordMutation = useMutation({
    mutationFn: ({ current, next }: { current: string; next: string }) =>
      changePassword(current, next),
    onSuccess: () => toast.show(t('settings.passwordChanged')),
  });

  function saveProfile(event: FormEvent) {
    event.preventDefault();
    profileMutation.mutate();
  }

  const currentUiLocale = i18n.language === 'en' ? 'en' : 'uk';
  const settings = bootstrapQuery.data?.settings;

  return (
    <div className={styles.page}>
      <PageHeader title={t('settings.title')} subtitle={t('settings.subtitle')} />

      <div className={styles.grid}>
        <Card>
          <h2 className={styles.sectionTitle}>{t('settings.profileTitle')}</h2>
          <form onSubmit={saveProfile} noValidate>
            <FormStack>
              <FormError>{profileMutation.isError ? t('errors.generic') : null}</FormError>
              <Input label={t('settings.email')} value={user?.email ?? ''} readOnly disabled />
              <Input
                label={t('settings.displayName')}
                hint={t('settings.displayNameHint')}
                value={displayName}
                onChange={(event) => setDisplayName(event.target.value)}
                maxLength={100}
              />
              <Select
                label={t('settings.locale')}
                value={locale}
                onChange={(event) => setLocaleField(event.target.value === 'en' ? 'en' : 'uk')}
                hint={locale !== currentUiLocale ? t('settings.localeAppliesOnSave') : undefined}
              >
                <option value="uk">{t('settings.localeUk')}</option>
                <option value="en">{t('settings.localeEn')}</option>
              </Select>
              <FormActions>
                <Button type="submit" loading={profileMutation.isPending}>
                  {t('common.save')}
                </Button>
              </FormActions>
            </FormStack>
          </form>
        </Card>

        <Card>
          <h2 className={styles.sectionTitle}>{t('settings.appearanceTitle')}</h2>
          <FormStack>
            <div>
              <div className={styles.label}>{t('settings.theme')}</div>
              <Tabs<'light' | 'dark'>
                aria-label={t('settings.theme')}
                options={[
                  { value: 'light', label: `☀ ${t('settings.themeLight')}` },
                  { value: 'dark', label: `☾ ${t('settings.themeDark')}` },
                ]}
                value={theme}
                onChange={(value) => {
                  if (value !== theme) toggleTheme();
                }}
              />
              <p className={styles.note}>{t('settings.themeNote')}</p>
            </div>
          </FormStack>

          <h2 className={`${styles.sectionTitle} ${styles.spaced}`}>{t('settings.gradesTitle')}</h2>
          <PropertyList
            rows={[
              {
                key: 'commemorative',
                label: t('settings.gradeCommemorative'),
                value: settings ? <Badge>{settings.defaultGradeCommemorative}</Badge> : '…',
              },
              {
                key: 'circulation',
                label: t('settings.gradeCirculation'),
                value: settings ? <Badge>{settings.defaultGradeCirculation}</Badge> : '…',
              },
            ]}
          />
          <p className={styles.note}>{t('settings.gradesNote')}</p>
        </Card>

        <Card>
          <h2 className={styles.sectionTitle}>{t('settings.passwordTitle')}</h2>
          <PasswordForm
            busy={passwordMutation.isPending}
            submitError={passwordMutation.error}
            onSubmit={(current, next) =>
              passwordMutation.mutateAsync({ current, next }).then(() => {})
            }
          />
        </Card>

        <Card>
          <h2 className={styles.sectionTitle}>{t('settings.accountTitle')}</h2>
          <FormStack>
            <FormRow>
              <div>
                <div className={styles.label}>{t('settings.role')}</div>
                <Badge tone={user?.role === 'admin' ? 'accent' : 'neutral'}>
                  {user?.role === 'admin' ? t('settings.roleAdmin') : t('settings.roleUser')}
                </Badge>
              </div>
            </FormRow>
            {user?.role === 'admin' ? (
              <div className={styles.adminBox}>
                <div className={styles.label}>{t('settings.adminTitle')}</div>
                <p className={styles.note}>{t('settings.adminText')}</p>
                <Link to="/admin">
                  <Button variant="secondary" size="sm">
                    {t('settings.adminLink')}
                  </Button>
                </Link>
              </div>
            ) : null}
            <FormActions>
              <Button variant="danger" onClick={() => void signOut()}>
                {t('header.logout')}
              </Button>
            </FormActions>
          </FormStack>
        </Card>
      </div>
    </div>
  );
}
