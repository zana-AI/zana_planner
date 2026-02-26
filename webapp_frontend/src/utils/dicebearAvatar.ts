/**
 * Generates a deterministic DiceBear toon-head avatar URL for a given user ID.
 */
export function getDicebearUrl(userId: string): string {
  const params = new URLSearchParams({
    seed: userId,
    size: '64',
    scale: '95',
    radius: '50',
    backgroundType: 'solid',
    // backgroundColor: '1e3a5f,2a4365,314e7e',
    hair: 'sideComed,spiky,undercut',
    hairProbability: '100',
    rearHairProbability: '0',
    beardProbability: '0',
    eyes: 'happy,humble,wide,wink',
    eyebrows: 'happy,neutral,raised',
    mouth: 'smile,laugh,agape',
    clothes: 'shirt,tShirt,openJacket,turtleNeck',
    // clothesColor: '0b3286,147f3c,545454,e8e9e6',
    hairColor: '2c1b18,724133,a55728,b58143',
    skinColor: 'a36b4f,b98e6a,c68e7a,f1c3a5',
  });
  return `https://api.dicebear.com/9.x/toon-head/svg?${params.toString()}`;
}
