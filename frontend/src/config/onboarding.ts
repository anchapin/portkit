/**
 * Onboarding Flow Configuration
 * Centralized config for all onboarding copy, branding, and quota strings.
 * Update values here to propagate across the entire onboarding experience.
 */

export const ONBOARDING_CONFIG = {
  branding: {
    productName: 'PortKit',
    tagline:
      'Convert your Minecraft Java mods to Bedrock add-ons in minutes, not months.',
  },

  // Conversion statistics (update from real metrics before public launch)
  stats: {
    automationRange: '60-80%', // Expected automation rate range
    conversionTimeRange: '5-30 min', // Typical conversion time range
    modsConvertedCount: '1000+', // Total mods converted (launch metric)
  },

  // Free tier limits (synced with PricingPage.tsx and ConversionUpload.tsx)
  freeTier: {
    conversionsPerMonth: 5,
    maxFileSizeMB: 100,
  },

  // Pro tier limits
  proTier: {
    maxFileSizeMB: 500,
  },

  // Upload checklist (synced with ConversionUpload.tsx MAX_FILE_SIZE_MB)
  uploadChecklist: [
    'Have your Java mod file ready (.jar or .zip)',
    'Make sure it works in Java Edition first',
    'Maximum file size: 100MB (Free), 500MB (Pro)',
  ],

  // File size limits displayed in onboarding
  fileSizeLimits: {
    free: '100MB',
    pro: '500MB',
  },
} as const;

export type OnboardingConfig = typeof ONBOARDING_CONFIG;
