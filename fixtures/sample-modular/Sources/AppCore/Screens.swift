import CharacterFeature
import EpisodeFeature
import Models

public enum Screens {
    public static func titles(character: Character, episode: Episode) -> [String] {
        [CharacterRow(character: character).title, EpisodeRow(episode: episode).title]
    }
}
