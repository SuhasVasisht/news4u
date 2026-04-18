import { PreferencesForm } from "@/components/settings/preferences-form";
import { getPreferences } from "@/lib/services/news-service";

export const dynamic = "force-dynamic";

export default async function SettingsPage() {
  const preferences = await getPreferences();
  return <PreferencesForm initialValues={preferences} />;
}
