# Sound effects that are recordings

Everything else this game plays is synthesised in `static/js/sound.js`. These
are not, and they are here rather than on the box - unlike the music - because
their licences permit redistribution, so they can be in git where a fresh
clone, CI and the deploy all get them for nothing.

## thunder.ogg

"Thunder crack 2B", recorded 17 April 2022 by **Jud McCranie**, from Wikimedia
Commons, **CC BY-SA 4.0**.

  https://commons.wikimedia.org/wiki/File:Thunder_crack_2B.ogg
  https://creativecommons.org/licenses/by-sa/4.0/

Trimmed to the 8.2 seconds around the strike, mixed to mono and normalised to
-16 LUFS with a -1.5 dBTP ceiling. That edit is a derivative work and is offered
under the same CC BY-SA 4.0 terms.

## ghost.ogg

Chinmay, laughing into a phone. Ours, so no third-party terms attach.

Trimmed to the laugh, high-passed at 140Hz, denoised (it is a phone in a room),
then **resampled to 1.45x rather than pitch-shifted** - which raises the pitch
and quickens it in one move, and the quickening is half of why it reads as a
cartoon ghost rather than a person. Normalised to -13 LUFS, -1.0 dBTP, mono.

To make it higher or lower, change the `asetrate` multiplier and re-encode; the
player applies only a little jitter on top so two ghosts are not identical.
