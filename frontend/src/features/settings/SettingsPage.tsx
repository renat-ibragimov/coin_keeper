import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Trash2 } from 'lucide-react';
import { useState } from 'react';
import type { FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import { useAuth } from '@/features/auth/useAuth';
import {
  addStorageLocation,
  deleteStorageLocation,
  fetchStorageLocations,
} from '@/features/collection/api';
import { GRADES } from '@/features/collection/grades';
import { fetchBootstrap } from '@/features/dashboard/api';
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
  FormActions,
  FormError,
  FormRow,
  FormStack,
  Input,
  PageHeader,
  Select,
  Tabs,
  Toggle,
  useToast,
} from '@/shared/ui';

import { changePassword, updateProfile, updateSettings } from './api';
import { PasswordForm } from './PasswordForm';
import styles from './SettingsPage.module.css';

export function SettingsPage() {
  const { t } = useTranslation();
  const { user, updateUser, signOut } = useAuth();
  const { preference, setPreference } = useTheme();
  const toast = useToast();
  const queryClient = useQueryClient();

  const bootstrapQuery = useQuery({ queryKey: ['bootstrap'], queryFn: fetchBootstrap });
  const storageLocationsQuery = useQuery({
    queryKey: ['collection', 'storage-locations'],
    queryFn: fetchStorageLocations,
  });
  const [displayName, setDisplayName] = useState(user?.displayName ?? '');
  const [storageLocationDraft, setStorageLocationDraft] = useState<string | null>(null);
  const [newLocationName, setNewLocationName] = useState('');
  const [locationToDelete, setLocationToDelete] = useState<string | null>(null);

  const catalogViewMode = useStoredViewMode('ck.viewMode.catalog', 'catalogViewMode');
  const collectionViewMode = useStoredViewMode('ck.viewMode.collection', 'collectionViewMode');

  const profileMutation = useMutation({
    mutationFn: () => updateProfile({ displayName: displayName.trim() || null }),
    onSuccess: (updated) => {
      updateUser(updated);
      toast.show(t('settings.profileSaved'));
    },
  });
  // Interface language lives with the appearance settings, not the profile
  // form: it applies the moment it's picked, same as the theme, instead of
  // waiting for a "Save" click that also touches the display name.
  const localeMutation = useMutation({
    mutationFn: (next: Locale) => updateProfile({ locale: next }),
    onSuccess: (updated) => {
      updateUser(updated);
      setLocale(updated.locale === 'en' ? 'en' : 'uk');
    },
    onError: () => toast.show(t('errors.generic')),
  });
  const passwordMutation = useMutation({
    mutationFn: ({ current, next }: { current: string; next: string }) =>
      changePassword(current, next),
    onSuccess: () => toast.show(t('settings.passwordChanged')),
  });
  const packagingMutation = useMutation({
    mutationFn: (showPackagingVariants: boolean) => updateSettings({ showPackagingVariants }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['bootstrap'] });
      void queryClient.invalidateQueries({ queryKey: ['catalog'] });
    },
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
  const addLocationMutation = useMutation({
    mutationFn: (name: string) => addStorageLocation(name),
    onSuccess: () => {
      setNewLocationName('');
      void queryClient.invalidateQueries({ queryKey: ['collection', 'storage-locations'] });
    },
    onError: () => toast.show(t('errors.generic')),
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

  function saveProfile(event: FormEvent) {
    event.preventDefault();
    profileMutation.mutate();
  }

  const settings = bootstrapQuery.data?.settings;
  const storageLocationValue = storageLocationDraft ?? settings?.defaultStorageLocation ?? '';

  function saveDefaultStorageLocation() {
    if (
      storageLocationDraft === null ||
      storageLocationDraft === settings?.defaultStorageLocation
    ) {
      return;
    }
    storageLocationMutation.mutate(storageLocationDraft);
  }

  function submitNewLocation(event: FormEvent) {
    event.preventDefault();
    const trimmed = newLocationName.trim();
    if (!trimmed) return;
    addLocationMutation.mutate(trimmed);
  }

  return (
    <div className={styles.page}>
      <PageHeader align="center" title={t('settings.title')} subtitle={t('settings.subtitle')} />

      <div className={styles.columns}>
        <div className={styles.column}>
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
                <FormActions>
                  <Button type="submit" loading={profileMutation.isPending}>
                    {t('common.save')}
                  </Button>
                </FormActions>
              </FormStack>
            </form>

            <h3 className={`${styles.subsectionTitle} ${styles.spaced}`}>
              {t('settings.passwordTitle')}
            </h3>
            <PasswordForm
              busy={passwordMutation.isPending}
              submitError={passwordMutation.error}
              onSubmit={(current, next) =>
                passwordMutation.mutateAsync({ current, next }).then(() => {})
              }
            />
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
              <p className={styles.note}>{t('settings.showPackagingVariantsNote')}</p>
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
                onBlur={saveDefaultStorageLocation}
              />
            </FormStack>

            <h3 className={`${styles.subsectionTitle} ${styles.spaced}`}>
              {t('settings.storageLocationsTitle')}
            </h3>
            <FormStack>
              <ul className={styles.locationList}>
                {(storageLocationsQuery.data ?? []).map((location) => (
                  <li key={location.name} className={styles.locationItem}>
                    <span>{location.name}</span>
                    {location.custom ? (
                      <Button
                        variant="ghost"
                        size="sm"
                        className={styles.iconButton}
                        aria-label={t('common.delete')}
                        onClick={() => setLocationToDelete(location.name)}
                      >
                        <Trash2 size={16} aria-hidden="true" />
                      </Button>
                    ) : null}
                  </li>
                ))}
              </ul>
              <form onSubmit={submitNewLocation} className={styles.addLocationForm}>
                <Input
                  aria-label={t('settings.storageLocationsTitle')}
                  placeholder={t('purchase.storageLocationPlaceholder')}
                  value={newLocationName}
                  onChange={(event) => setNewLocationName(event.target.value)}
                  maxLength={200}
                />
                <Button type="submit" size="sm" loading={addLocationMutation.isPending}>
                  {t('common.add')}
                </Button>
              </form>
            </FormStack>
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
