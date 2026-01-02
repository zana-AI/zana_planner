/**
 * Deterministic username generator for users without names.
 * Generates Reddit-style two-word usernames (adjective + noun) based on user_id.
 * Same user_id always generates the same username.
 */

const ADJECTIVES = [
  'Swift', 'Bold', 'Clever', 'Bright', 'Noble', 'Wise', 'Calm', 'Brave',
  'Fierce', 'Gentle', 'Radiant', 'Serene', 'Vivid', 'Eager', 'Loyal', 'Proud',
  'Daring', 'Humble', 'Vibrant', 'Steady', 'Quick', 'Silent', 'Mighty', 'Graceful',
  'Bold', 'Kind', 'Sharp', 'Wild', 'Pure', 'Fresh', 'Solid', 'Rapid',
  'Smooth', 'Crisp', 'Warm', 'Cool', 'Bright', 'Deep', 'High', 'Low',
  'Strong', 'Light', 'Dark', 'Clear', 'Firm', 'Soft', 'Hard', 'Smooth',
  'Rough', 'Fine', 'Coarse', 'Thick', 'Thin', 'Wide', 'Narrow', 'Tall',
  'Short', 'Long', 'Big', 'Small', 'Huge', 'Tiny', 'Giant', 'Mini',
  'Fast', 'Slow', 'Quick', 'Lazy', 'Active', 'Quiet', 'Loud', 'Silent',
  'Happy', 'Joyful', 'Cheerful', 'Merry', 'Gleeful', 'Jolly', 'Blissful', 'Ecstatic'
];

const NOUNS = [
  'Eagle', 'Phoenix', 'Star', 'Wave', 'Mountain', 'River', 'Forest', 'Light',
  'Thunder', 'Storm', 'Ocean', 'Sky', 'Moon', 'Sun', 'Wind', 'Fire',
  'Stone', 'Crystal', 'Diamond', 'Pearl', 'Gold', 'Silver', 'Steel', 'Iron',
  'Tiger', 'Lion', 'Wolf', 'Bear', 'Hawk', 'Falcon', 'Raven', 'Owl',
  'Dragon', 'Unicorn', 'Griffin', 'Phoenix', 'Sphinx', 'Basilisk', 'Hydra', 'Kraken',
  'Sword', 'Shield', 'Arrow', 'Bow', 'Spear', 'Axe', 'Hammer', 'Blade',
  'Crown', 'Throne', 'Castle', 'Tower', 'Temple', 'Shrine', 'Altar', 'Sanctuary',
  'Path', 'Road', 'Trail', 'Journey', 'Quest', 'Adventure', 'Voyage', 'Expedition',
  'Dream', 'Vision', 'Hope', 'Faith', 'Courage', 'Honor', 'Glory', 'Victory',
  'Wisdom', 'Knowledge', 'Truth', 'Justice', 'Freedom', 'Peace', 'Harmony', 'Balance'
];

/**
 * Simple hash function for deterministic index generation.
 */
function hashUserId(userId: string): number {
  let hash = 0;
  for (let i = 0; i < userId.length; i++) {
    const char = userId.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash = hash & hash; // Convert to 32-bit integer
  }
  return Math.abs(hash);
}

/**
 * Generate a deterministic username from user_id.
 * Format: "AdjectiveNoun" (e.g., "SwiftEagle", "BoldPhoenix")
 * 
 * @param userId - The user ID as a string
 * @returns A two-word username
 */
export function generateUsername(userId: string): string {
  const hash = hashUserId(userId);
  
  // Use hash to select adjective and noun deterministically
  const adjectiveIndex = hash % ADJECTIVES.length;
  const nounIndex = Math.floor(hash / ADJECTIVES.length) % NOUNS.length;
  
  const adjective = ADJECTIVES[adjectiveIndex];
  const noun = NOUNS[nounIndex];
  
  return `${adjective}${noun}`;
}

/**
 * Extract initials from a generated username.
 * For "SwiftEagle", returns "SE"
 * 
 * @param username - The generated username
 * @returns Two-letter initials
 */
export function getInitialsFromUsername(username: string): string {
  // Split on capital letters to get words
  const words = username.split(/(?=[A-Z])/);
  if (words.length >= 2) {
    return (words[0][0] + words[1][0]).toUpperCase();
  }
  return username[0]?.toUpperCase() || '?';
}

