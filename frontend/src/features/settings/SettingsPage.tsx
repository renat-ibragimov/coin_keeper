import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router-dom';

import * as authApi from '@/features/auth/api';
import { useAuth } from '@/features/auth/useAuth';
import { deleteStorageLocation, fetchStorageLocations } from '@/features/collection/api';
import { GRADES } from '@/features/collection/grades';
import { fetchBootstrap } from '@/features/dashboard/api';
import type { SessionOut } from '@/shared/api/types';
import { setLocale } from '@/shared/i18n';
import type { Locale } from '@/shared/i18n';
import { useStoredViewMode } from '@/shared/lib/useStoredViewMode';
import { useTheme } from '@/shared/theme/useTheme';
import type { ThemePreference } from '@/shared/theme/themeContext';
import {
  Badge,
  Button,
  Card,
  Combobox,
  ConfirmDialog,
  FormRow,
  FormStack,
  Input,
  PageHeader,
  Select,
  Tabs,
  Toggle,
  useToast,
} from '@/shared/ui';

import { changePassword, setPassword, updateProfile, updateSettings } from './api';
import { AvatarSection } from './AvatarSection';
import { PasswordForm } from './PasswordForm';
import styles from './SettingsPage.module.css';

export function SettingsPage() {
  const { t } = useTranslation();
  const { user, updateUser, acceptSession } = useAuth();
  const { preference, setPreference } = useTheme();
  const toast = useToast();
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const googleResult = searchParams.get('google');
  const googleStatus = useQuery({ queryKey: ['google-status'], queryFn: authApi.googleStatus });

  useEffect(() => {
    if (googleResult === 'linked') toast.show(t('settings.googleLinked'));
    else if (googleResult) toast.show(t('settings.googleLinkFailed'));
    if (googleResult) {
      const next = new URLSearchParams(searchParams);
      next.delete('google');
      setSearchParams(next, { replace: true });
    }
  }, [googleResult, searchParams, setSearchParams, t, toast]);

  const bootstrapQuery = useQuery({ queryKey: ['bootstrap'], queryFn: fetchBootstrap });
  const storageLocationsQuery = useQuery({
    queryKey: ['collection', 'storage-locations'],
    queryFn: fetchStorageLocations,
  });
  const [displayName, setDisplayName] = useState(user?.displayName ?? '');
  const [storageLocationDraft, setStorageLocationDraft] = useState<string | null>(null);
  const [locationToDelete, setLocationToDelete] = useState<string | null>(null);

  const catalogViewMode = useStoredViewMode('ck.viewMode.catalog', 'catalogViewMode');
  const collectionViewMode = useStoredViewMode('ck.viewMode.collection', 'collectionViewMode');

  const profileMutation = useMutation({
    mutationFn: (name: string | null) => updateProfile({ displayName: name }),
    onSuccess: (updated) => {
      updateUser(updated);
      toast.show(t('settings.profileSaved'));
    },
    // Every other control on this page reports failure the same way; without
    // a form around the field there is no FormError slot to put it in.
    onError: () => toast.show(t('errors.generic')),
  });
  // Interface language lives with the appearance settings, not the profile
  // form: it applies the moment it's picked, same as the theme, instead of
  // waiting for a "Save" click that also touches the display name.
  const localeMutation = useMutation({
    mutationFn: (next: Locale) => updateProfile({ locale: next }),
    onSuccess: (updated) => {
      updateUser(updated);
      setLocale(updated.locale === 'en' ? 'en' : 'uk');
      // Every name the server sends (grades aside) is localized -- storage
      // locations here, coin/series/country titles elsewhere. None of those
      // query keys carry the locale, so nothing refetches on its own; without
      // this, a page that doesn't fully remount (this one) keeps showing
      // names in the language the user just left.
      void queryClient.invalidateQueries();
    },
    onError: () => toast.show(t('errors.generic')),
  });
  const passwordMutation = useMutation({
    mutationFn: ({
      current,
      next,
    }: {
      current: string;
      next: string;
    }): Promise<SessionOut | void> =>
      user?.hasPassword === false ? setPassword(next) : changePassword(current, next),
    onSuccess: (session) => {
      if (session) acceptSession(session);
      else if (user?.hasPassword === false) updateUser({ ...user, hasPassword: true });
      toast.show(t('settings.passwordChanged'));
    },
  });

  const googleLinkMutation = useMutation({
    mutationFn: authApi.startGoogleLink,
    onSuccess: ({ url }) => {
      window.location.assign(url);
    },
    onError: () => toast.show(t('settings.googleLinkFailed')),
  });
  const packagingMutation = useMutation({
    mutationFn: (showPackagingVariants: boolean) => updateSettings({ showPackagingVariants }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['bootstrap'] });
      void queryClient.invalidateQueries({ queryKey: ['catalog'] });
    },
  });
  const includeSupportingExpensesMutation = useMutation({
    mutationFn: (includeSupportingExpenses: boolean) =>
      updateSettings({ includeSupportingExpenses }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['bootstrap'] }),
  });
  const gradeMutation = useMutation({
    mutationFn: (defaultGrade: string) => updateSettings({ defaultGrade }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['bootstrap'] }),
  });
  const themeMutation = useMutation({
    mutationFn: (theme: ThemePreference) => updateSettings({ theme }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['bootstrap'] }),
  });
  const secondaryCurrencyMutation = useMutation({
    mutationFn: (secondaryCurrency: 'USD' | 'EUR') => updateSettings({ secondaryCurrency }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['bootstrap'] }),
  });
  const storageLocationMutation = useMutation({
    mutationFn: (defaultStorageLocation: string) => updateSettings({ defaultStorageLocation }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['bootstrap'] });
      void queryClient.invalidateQueries({ queryKey: ['collection', 'storage-locations'] });
    },
  });
  const deleteLocationMutation = useMutation({
    mutationFn: (name: string) => deleteStorageLocation(name),
    onSuccess: () => {
      setLocationToDelete(null);
      void queryClient.invalidateQueries({ queryKey: ['collection', 'storage-locations'] });
      void queryClient.invalidateQueries({ queryKey: ['bootstrap'] });
    },
    onError: () => {
      toast.show(t('errors.generic'));
      setLocationToDelete(null);
    },
  });

  function changeTheme(next: ThemePreference) {
    setPreference(next);
    themeMutation.mutate(next);
  }

  // The same commit pair as «Місце зберігання» below: Enter saves, and so
  // does clicking away — a name typed and then abandoned without pressing
  // Enter must not disappear silently. An unchanged value sends nothing, or
  // every stray click through the field would be a PATCH.
  function saveDisplayName() {
    const next = displayName.trim() || null;
    if (next === (user?.displayName ?? null)) return;
    profileMutation.mutate(next);
  }

  const settings = bootstrapQuery.data?.settings;
  const storageLocationValue = storageLocationDraft ?? settings?.defaultStorageLocation ?? '';

  // Mirrors the filter-panel draft pattern (CatalogPage/CollectionPage): once
  // the server value moves -- our own save lands, a locale switch relabels
  // it, another tab changes it -- the local draft must let go, or it keeps
  // shadowing the real value for the rest of the session.
  useEffect(() => {
    setStorageLocationDraft(null);
  }, [settings?.defaultStorageLocation]);

  function saveDefaultStorageLocationValue(value: string) {
    if (value === (settings?.defaultStorageLocation ?? '')) return;
    storageLocationMutation.mutate(value);
  }

  function saveDefaultStorageLocation() {
    if (storageLocationDraft === null) return;
    saveDefaultStorageLocationValue(storageLocationDraft);
  }

  return (
    <div className={styles.page}>
      <PageHeader align="center" title={t('settings.title')} subtitle={t('settings.subtitle')} />

      <div className={styles.columns}>
        <div className={styles.column}>
          <Card>
            <h2 className={styles.sectionTitle}>
              {t('settings.profileTitle')}
              <Badge tone={user?.role === 'admin' ? 'accent' : 'neutral'}>
                {user?.role === 'admin' ? t('settings.roleAdmin') : t('settings.roleUser')}
              </Badge>
            </h2>
            <AvatarSection />
            <FormStack>
              <Input label={t('settings.email')} value={user?.email ?? ''} readOnly disabled />
              <Input
                label={t('settings.displayName')}
                hint={t('settings.displayNameHint')}
                value={displayName}
                onChange={(event) => setDisplayName(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') {
                    event.preventDefault();
                    saveDisplayName();
                  }
                }}
                onBlur={saveDisplayName}
                maxLength={100}
              />
            </FormStack>

            <h3 className={`${styles.subsectionTitle} ${styles.spaced}`}>
              {t('settings.passwordTitle')}
            </h3>
            <PasswordForm
              busy={passwordMutation.isPending}
              submitError={passwordMutation.error}
              requireCurrent={user?.hasPassword !== false}
              onSubmit={(current, next) =>
                passwordMutation.mutateAsync({ current, next }).then(() => {})
              }
            />
            {googleStatus.data?.enabled ? (
              <div>
                <h3 className={`${styles.subsectionTitle} ${styles.spaced}`}>
                  {t('settings.googleTitle')}
                </h3>
                {user?.googleLinked ? (
                  <p>{t('settings.googleLinked')}</p>
                ) : (
                  <Button
                    type="button"
                    variant="secondary"
                    loading={googleLinkMutation.isPending}
                    onClick={() => googleLinkMutation.mutate()}
                  >
                    {t('settings.googleLink')}
                  </Button>
                )}
              </div>
            ) : null}
          </Card>
        </div>

        <div className={styles.column}>
          <Card>
            <h2 className={styles.sectionTitle}>{t('settings.appearanceTitle')}</h2>
            <FormStack>
              <div>
                <div className={styles.label}>{t('settings.theme')}</div>
                <Tabs<'light' | 'dark' | 'system'>
                  aria-label={t('settings.theme')}
                  options={[
                    { value: 'light', label: `☀ ${t('settings.themeLight')}` },
                    { value: 'dark', label: `☾ ${t('settings.themeDark')}` },
                    { value: 'system', label: t('settings.themeSystem') },
                  ]}
                  value={preference}
                  onChange={changeTheme}
                />
              </div>
              <Select
                label={t('settings.locale')}
                value={user?.locale === 'en' ? 'en' : 'uk'}
                disabled={localeMutation.isPending}
                onChange={(event) => {
                  const next: Locale = event.target.value === 'en' ? 'en' : 'uk';
                  localeMutation.mutate(next);
                }}
              >
                <option value="uk">{t('settings.localeUk')}</option>
                <option value="en">{t('settings.localeEn')}</option>
              </Select>
              <Select
                label={t('settings.secondaryCurrency')}
                value={settings?.secondaryCurrency === 'EUR' ? 'EUR' : 'USD'}
                disabled={!settings || secondaryCurrencyMutation.isPending}
                onChange={(event) =>
                  secondaryCurrencyMutation.mutate(event.target.value === 'EUR' ? 'EUR' : 'USD')
                }
              >
                <option value="USD">{t('settings.secondaryCurrencyUsd')}</option>
                <option value="EUR">{t('settings.secondaryCurrencyEur')}</option>
              </Select>
            </FormStack>
          </Card>

          <Card>
            <h2 className={styles.sectionTitle}>{t('settings.catalogPrefsTitle')}</h2>

            <h3 className={styles.subsectionTitle}>{t('settings.viewModeTitle')}</h3>
            <FormStack>
              <FormRow>
                <Select
                  label={t('settings.viewModeCatalog')}
                  value={settings?.catalogViewMode ?? 'cards'}
                  disabled={!settings}
                  onChange={(event) =>
                    catalogViewMode.remember(event.target.value === 'table' ? 'table' : 'cards')
                  }
                >
                  <option value="cards">{t('catalog.viewCards')}</option>
                  <option value="table">{t('catalog.viewTable')}</option>
                </Select>
                <Select
                  label={t('settings.viewModeCollection')}
                  value={settings?.collectionViewMode ?? 'cards'}
                  disabled={!settings}
                  onChange={(event) =>
                    collectionViewMode.remember(event.target.value === 'table' ? 'table' : 'cards')
                  }
                >
                  <option value="cards">{t('catalog.viewCards')}</option>
                  <option value="table">{t('catalog.viewTable')}</option>
                </Select>
              </FormRow>
            </FormStack>

            <h3 className={`${styles.subsectionTitle} ${styles.spaced}`}>
              {t('settings.gradesTitle')}
            </h3>
            <FormStack>
              <Select
                aria-label={t('settings.gradesTitle')}
                value={settings?.defaultGrade ?? 'UNC'}
                disabled={!settings || gradeMutation.isPending}
                onChange={(event) => gradeMutation.mutate(event.target.value)}
              >
                {GRADES.map((grade) => (
                  <option key={grade} value={grade}>
                    {t(`grades.${grade}`)}
                  </option>
                ))}
              </Select>
            </FormStack>

            <h3 className={`${styles.subsectionTitle} ${styles.spaced}`}>
              {t('settings.packagingTitle')}
            </h3>
            <FormStack>
              <Toggle
                checked={settings?.showPackagingVariants ?? true}
                disabled={!settings || packagingMutation.isPending}
                onChange={(checked) => packagingMutation.mutate(checked)}
                label={t('settings.showPackagingVariants')}
              />
            </FormStack>

            <h3 className={`${styles.subsectionTitle} ${styles.spaced}`}>
              {t('settings.valuationTitle')}
            </h3>
            <FormStack>
              <Toggle
                checked={settings?.includeSupportingExpenses ?? true}
                disabled={!settings || includeSupportingExpensesMutation.isPending}
                onChange={(checked) => includeSupportingExpensesMutation.mutate(checked)}
                label={t('settings.includeSupportingExpenses')}
              />
            </FormStack>

            <h3 className={`${styles.subsectionTitle} ${styles.spaced}`}>
              {t('settings.defaultStorageLocationTitle')}
            </h3>
            <FormStack>
              <Combobox
                aria-label={t('settings.defaultStorageLocationTitle')}
                placeholder={t('purchase.storageLocationPlaceholder')}
                options={(storageLocationsQuery.data ?? []).map((location) => location.name)}
                value={storageLocationValue}
                disabled={!settings}
                onChange={(event) => setStorageLocationDraft(event.target.value)}
                // Fires on an explicit pick (click/Enter on a suggestion) or
                // Enter on freshly typed text -- either way, later than
                // onBlur, which stays as the fallback for clicking away
                // without pressing Enter.
                onCommitValue={saveDefaultStorageLocationValue}
                onBlur={saveDefaultStorageLocation}
                isOptionDeletable={(option) =>
                  (storageLocationsQuery.data ?? []).some((l) => l.name === option && l.custom)
                }
                onDeleteOption={(option) => setLocationToDelete(option)}
                deleteOptionLabel={t('common.delete')}
                addNewLabel={t('settings.addStorageLocation')}
                createHint={(typed) => t('settings.storageLocationCreateHint', { name: typed })}
              />
            </FormStack>
          </Card>
        </div>
      </div>

      <ConfirmDialog
        open={locationToDelete !== null}
        title={t('settings.deleteStorageLocationTitle')}
        confirmLabel={t('common.delete')}
        onCancel={() => setLocationToDelete(null)}
        onConfirm={() => locationToDelete && deleteLocationMutation.mutate(locationToDelete)}
        busy={deleteLocationMutation.isPending}
        danger
      >
        {locationToDelete ? (
          <p>{t('settings.deleteStorageLocationText', { name: locationToDelete })}</p>
        ) : null}
      </ConfirmDialog>
    </div>
  );
}
