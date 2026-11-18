import Models

public struct EpisodeRow: Equatable {
    public let title: String

    public init(episode: Episode) {
        title = "\(episode.code): \(episode.title)"
    }
}
